"""Meningsbærende feil: ord som endrer betydningen når de faller ut eller endres.

WER teller alle ord likt. I et rettsdokument er det verre å miste «ikke», et
beløp eller et navn enn et småord. Denne modulen justerer fasit og modellsvar
mot hverandre (normalisert, lesbar profil) og teller per kategori:

- ``negation``: nektende ord i fasiten (ikke, ingen, aldri, nei ...). Tapt når
  ordet er utelatt eller erstattet med noe som ikke er en nektelse. Den faste
  frasen «ikke sant» er et innskudd, ikke en nektelse, og telles ikke.
  ``added`` teller nektelser modellen skrev uten at de står i fasiten.
- ``number``: tall i fasiten (etter at tallord er gjort om til sifre). Tapt når
  tallet mangler eller er et annet tall. Tallet 1 telles ikke, fordi «en» og
  «ett» oftest er ubestemt artikkel og blir 1 i normaliseringen.
- ``name``: ord med stor forbokstav i den rå fasiten, unntatt første ord i en
  setning. Et grovt mål på navn; tapt når ordet ikke står på samme plass i
  svaret.
"""

from __future__ import annotations

import re

from .normalize import normalize

NEGATIONS = frozenset(
    {
        "ikke", "ikkje", "ingen", "inga", "intet", "ingenting", "inkje", "ingenteing",
        "aldri", "nei", "verken", "hverken", "korkje", "uten", "utan",
    }
)

CATEGORIES = ("negation", "number", "name")

_SENTENCE_START_RE = re.compile(r"(?:^|[.!?:]\s+)(\S+)")
_CAP_WORD_RE = re.compile(r"\b[A-ZÆØÅ][a-zæøåéü]+(?:-[A-ZÆØÅ]?[a-zæøåéü]+)*\b")


def align_ops(reference: list[str], hypothesis: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Levenshtein-justering med sti: liste av (op, ref-ord, svar-ord), der op
    er ``ok``, ``sub``, ``del`` eller ``ins``. Samme kostnader og prioritet som
    ``metrics.align_counts`` (erstatning, så utelatelse, så innsetting)."""
    n, m = len(reference), len(hypothesis)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                cost[i][j] = cost[i - 1][j - 1]
            else:
                cost[i][j] = 1 + min(cost[i - 1][j - 1], cost[i - 1][j], cost[i][j - 1])
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and reference[i - 1] == hypothesis[j - 1] and cost[i][j] == cost[i - 1][j - 1]:
            ops.append(("ok", reference[i - 1], hypothesis[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + 1:
            ops.append(("sub", reference[i - 1], hypothesis[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            ops.append(("del", reference[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, hypothesis[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def name_words(raw_reference: str) -> set[str]:
    """Normaliserte ord som er skrevet med stor forbokstav i den rå fasiten,
    utenom første ord i hver setning."""
    starts = {m.group(1).strip("«»\"'()") for m in _SENTENCE_START_RE.finditer(raw_reference or "")}
    out = set()
    for w in _CAP_WORD_RE.findall(raw_reference or ""):
        if w in starts:
            continue
        for part in normalize(w).split():
            if not part.isdigit():
                out.add(part)
    return out


def _tag_in_hyp(ops, word) -> bool:
    """Sant hvis modellsvaret bruker ordet bare i «ikke sant»."""
    hyp = [h for op, _, h in ops if op != "del"]
    uses = [i for i, w in enumerate(hyp) if w == word]
    return bool(uses) and all(i + 1 < len(hyp) and hyp[i + 1] == "sant" for i in uses)


def critical_counts(raw_reference: str, reference_norm: str, hypothesis_norm: str) -> dict:
    """Antall meningsbærende ord i fasiten og hvor mange som gikk tapt."""
    ops = align_ops(reference_norm.split(), hypothesis_norm.split())
    names = name_words(raw_reference)
    out = {c: {"reference": 0, "missed": 0} for c in CATEGORIES}
    out["negation"]["added"] = 0
    ref_words = [r for op, r, _ in ops if op != "ins"]
    tag = set()  # posisjoner i fasiten der «ikke» er del av «ikke sant»
    for k, w in enumerate(ref_words[:-1]):
        if w in ("ikke", "ikkje") and ref_words[k + 1] == "sant":
            tag.add(k)
    k = -1
    for op, r, h in ops:
        if op != "ins":
            k += 1
        if op == "ins":
            if h in NEGATIONS and not _tag_in_hyp(ops, h):
                out["negation"]["added"] += 1
            continue
        if op == "sub" and h in NEGATIONS and r not in NEGATIONS:
            out["negation"]["added"] += 1
        lost = op in ("del", "sub")
        if r in NEGATIONS and k not in tag:
            out["negation"]["reference"] += 1
            if lost and not (op == "sub" and h in NEGATIONS):
                out["negation"]["missed"] += 1
        if r.isdigit() and r != "1":
            out["number"]["reference"] += 1
            out["number"]["missed"] += lost
        if r in names:
            out["name"]["reference"] += 1
            out["name"]["missed"] += lost
    return out


def add_counts(total: dict, part: dict) -> dict:
    for c, v in part.items():
        t = total.setdefault(c, {})
        for k, n in v.items():
            t[k] = t.get(k, 0) + n
    return total


def rates(total: dict) -> dict:
    """Legger til andel tapte per kategori."""
    out = {}
    for c, v in total.items():
        ref = v.get("reference", 0)
        out[c] = {**v, "missed_rate": round(v.get("missed", 0) / ref, 6) if ref else None}
    return out
