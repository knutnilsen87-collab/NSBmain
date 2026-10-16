"""Feilmål for talegjenkjenning: WER, CER og tegn på hallusinasjon.

Alt beregnes uten eksterne avhengigheter, slik at tallene kan etterprøves.
WER og CER summeres over hele testsettet (ikke snitt per setning).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

__all__ = [
    "EditCounts",
    "align_counts",
    "char_counts",
    "item_flags",
    "repetition_loop",
    "word_counts",
]


@dataclass
class EditCounts:
    """Antall erstatninger, utelatelser og innsettinger mot en fasit."""

    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    reference_length: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def error_rate(self) -> float:
        if self.reference_length == 0:
            return 0.0 if self.errors == 0 else float("inf")
        return self.errors / self.reference_length

    def __add__(self, other: EditCounts) -> EditCounts:
        return EditCounts(
            self.substitutions + other.substitutions,
            self.deletions + other.deletions,
            self.insertions + other.insertions,
            self.reference_length + other.reference_length,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["errors"] = self.errors
        return d


def align_counts(reference: list, hypothesis: list) -> EditCounts:
    """Levenshtein-justering med opptelling av S, D og I.

    Ved like kostnader foretrekkes erstatning, deretter utelatelse, deretter
    innsetting. Det gir samme totale feiltall som jiwer.
    """
    n, m = len(reference), len(hypothesis)
    # dp[i][j] = (kostnad, S, D, I) for reference[:i] mot hypothesis[:j]
    prev = [(j, 0, 0, j) for j in range(m + 1)]
    for i in range(1, n + 1):
        cur = [(i, 0, i, 0)] + [None] * m
        r = reference[i - 1]
        for j in range(1, m + 1):
            if r == hypothesis[j - 1]:
                cur[j] = prev[j - 1]
                continue
            c_sub, s, d, ins = prev[j - 1]
            best = (c_sub + 1, s + 1, d, ins)
            c_del, s, d, ins = prev[j]
            if c_del + 1 < best[0]:
                best = (c_del + 1, s, d + 1, ins)
            c_ins, s, d, ins = cur[j - 1]
            if c_ins + 1 < best[0]:
                best = (c_ins + 1, s, d, ins + 1)
            cur[j] = best
        prev = cur
    _, s, d, ins = prev[m]
    return EditCounts(s, d, ins, n)


def word_counts(reference: str, hypothesis: str) -> EditCounts:
    """Ordnivå. Begge tekstene må være normalisert på forhånd."""
    return align_counts(reference.split(), hypothesis.split())


def char_counts(reference: str, hypothesis: str) -> EditCounts:
    """Tegnnivå, med mellomrom som eget tegn. Begge tekstene normalisert."""
    return align_counts(list(reference), list(hypothesis))


def repetition_loop(words: list, min_repeats: int = 4, max_ngram: int = 4) -> bool:
    """Sant hvis samme n-gram (n = 1..max_ngram) gjentas minst min_repeats
    ganger etter hverandre. Typisk tegn på at modellen har låst seg."""
    total = len(words)
    for n in range(1, max_ngram + 1):
        if total < n * min_repeats:
            break
        for start in range(total - n * min_repeats + 1):
            gram = words[start : start + n]
            repeats = 1
            pos = start + n
            while pos + n <= total and words[pos : pos + n] == gram:
                repeats += 1
                pos += n
                if repeats >= min_repeats:
                    return True
    return False


def item_flags(reference: str, hypothesis: str, counts: EditCounts) -> dict:
    """Flagg per setning. Tekstene er normalisert.

    - ``hallucination_on_silence``: fasiten er tom, men modellen skrev noe
    - ``repetition_loop``: samme frase gjentatt minst fire ganger på rad
    - ``overlong``: svaret har mer enn dobbelt så mange ord som fasiten pluss fem
    - ``empty_output``: fasiten har tekst, men modellen skrev ingenting
    - ``hallucination``: ett av de tre første flaggene
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    on_silence = not ref_words and bool(hyp_words)
    loop = repetition_loop(hyp_words)
    overlong = len(hyp_words) > 2 * len(ref_words) + 5
    return {
        "hallucination_on_silence": on_silence,
        "repetition_loop": loop,
        "overlong": overlong,
        "empty_output": bool(ref_words) and not hyp_words,
        "hallucination": on_silence or loop or overlong,
        "insertion_ratio": counts.insertions / max(1, len(ref_words)),
    }
