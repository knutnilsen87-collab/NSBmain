"""Dekodingsprofiler og vakt mot gjentakelsesløkker.

Brukes både av målestokken (``nsb_eval.runner --decoding``) og talemotoren
(``nsb_engine.server --decoding``), så det som måles er det som kjøres.

Profiler:

- ``standard``: grådig/strålesøk ved temperatur 0, slik alle tidligere målinger er gjort.
- ``loopvakt``: som standard, men en segmentdekoding som blir for repetitiv
  (kompresjonsforhold over 2,4, samme grense som Whisper selv bruker) dekodes på
  nytt ved temperatur 0,2 og 0,4. Lav sannsynlighet alene utløser ikke ny dekoding.
- ``loopvakt_ngram``: som ``loopvakt``, og i tillegg kan ingen sekvens på fire ord
  gjentas innenfor samme segment.

Alle profiler kan kombineres med ``collapse_loops``: en frase som gjentas fire
ganger eller mer etter hverandre, kortes ned til to. Fasitene i NB Samtale har
gjentakelser som «er du er du» (to ganger) og «takk takk takk» (tre), som beholdes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

PROFILES: dict[str, dict] = {
    "standard": {"temperature": 0.0},
    "loopvakt": {"temperature": (0.0, 0.2, 0.4), "compression_ratio_threshold": 2.4, "log_prob_threshold": None},
    "loopvakt_ngram": {"temperature": (0.0, 0.2, 0.4), "compression_ratio_threshold": 2.4, "log_prob_threshold": None,
                       "no_repeat_ngram_size": 4},
}

MIN_REPEATS = 4
KEEP = 2
MAX_NGRAM = 12


def profile(name: str) -> dict:
    if name not in PROFILES:
        raise ValueError(f"ukjent dekodingsprofil {name!r}; velg {', '.join(PROFILES)}")
    return dict(PROFILES[name])


def collapse_loops(items: Sequence[T], key: Callable[[T], str] = lambda x: x,  # type: ignore[assignment,return-value]
                   min_repeats: int = MIN_REPEATS, keep: int = KEEP, max_ngram: int = MAX_NGRAM) -> list[T]:
    """Korter ned fraser som gjentas ``min_repeats`` ganger eller mer etter hverandre til ``keep``.

    Virker på ord (str) eller ordobjekter med ``key`` (for eksempel talemotorens
    ``Word`` med tider). Sammenligningen ignorerer store/små bokstaver og tegnsetting.
    """
    norm = ["".join(ch for ch in key(x).lower() if ch.isalnum()) for x in items]
    out: list[T] = []
    i, total = 0, len(items)
    while i < total:
        best = None
        for n in range(1, max_ngram + 1):
            if i + n * min_repeats > total:
                break
            gram = norm[i:i + n]
            if not any(gram):
                continue
            reps, pos = 1, i + n
            while pos + n <= total and norm[pos:pos + n] == gram:
                reps += 1
                pos += n
            if reps >= min_repeats:
                best = (n, reps)
                break
        if best:
            n, reps = best
            out.extend(items[i:i + n * keep])
            i += n * reps
        else:
            out.append(items[i])
            i += 1
    return out


def collapse_text(text: str) -> str:
    return " ".join(collapse_loops(text.split()))
