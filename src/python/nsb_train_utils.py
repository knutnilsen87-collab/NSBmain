"""Rene hjelpefunksjoner for Whisper-trening, uten avhengighet til torch.

Holdes adskilt fra ``train_whisper_iterable.py`` slik at de kan testes i CI.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Iterable, Iterator

__all__ = [
    "PUNCTUATION_WORDS",
    "clean_training_text",
    "shuffle_buffer",
    "strip_decoder_start",
    "group_bucket",
    "validate_out_dir",
]

# NST-diktat: talerne leste tegnsetting høyt. Fasiten er «kontroll,\Komma».
PUNCTUATION_WORDS = {
    "komma": ",",
    "punktum": ".",
    "spørsmålstegn": "?",
    "utropstegn": "!",
    "kolon": ":",
    "semikolon": ";",
    "tankestrek": "–",
    "bindestrek": "-",
    "anførselstegn": '"',
    "parentes": "(",
}

_SILENCE_PROMPT_RE = re.compile(r"^\(\s*\.{0,3}.*\.{0,3}\s*\)$")
_DICTATED_PUNCT_RE = re.compile(r"\\(" + "|".join(PUNCTUATION_WORDS) + r")\b", flags=re.IGNORECASE)
_DOUBLE_NOTATION_RE = re.compile(r"(\S+)\\(\S+)")
_TRUNCATED_RE = re.compile(r"\S*£")
_UNCERTAIN_RE = re.compile(r"<inaudible>|%unint|%unk|%foreign|\[uhørbart\]", flags=re.IGNORECASE)
_ANNOTATION_RE = re.compile(r"<[^>]*>|%\w+")
_SPACE_RE = re.compile(r"\s+")


def clean_training_text(text: str | None, dictation: str = "symbol") -> tuple[str | None, str]:
    """Renser en fasit for trening. Gir ``(tekst, grunn)``.

    ``tekst`` er ``None`` når setningen ikke skal brukes; ``grunn`` sier hvorfor
    (eller ``"ok"``). Regler:

    - NSTs stille opptak («(...Vær stille under dette opptaket...)») og andre
      fasiter som bare er en parentes forkastes: de lærer modellen å finne på
      tekst i stillhet.
    - Fasiter med usikre partier (``<INAUDIBLE>``, ``%unint``, ``%foreign``)
      forkastes.
    - Uttalt tegnsetting (``kontroll,\\Komma``): ``dictation="symbol"`` gir
      «kontroll,» (diktatmodus, som EVIDA trenger); ``"word"`` gir
      «kontroll komma» (ordrett).
    - NB Samtales ``sagt\\skriftlig`` erstattes med skriftlig form.
    - Avbrutte ord (``ble£``), ``+``-markører og fyllord-annotasjoner fjernes.
    """
    if text is None:
        return None, "empty"
    t = text.strip()
    if not t:
        return None, "empty"
    if _SILENCE_PROMPT_RE.match(t):
        return None, "silence_prompt"
    if _UNCERTAIN_RE.search(t):
        return None, "uncertain_segment"
    if dictation == "word":
        t = _DICTATED_PUNCT_RE.sub(lambda m: " " + m.group(1).lower(), t)
        t = re.sub(r"[,.?!:;]+(?=\s+(?:" + "|".join(PUNCTUATION_WORDS) + r")\b)", "", t)
    elif dictation == "symbol":
        t = _DICTATED_PUNCT_RE.sub("", t)
    else:
        raise ValueError(f"ukjent dictation-modus: {dictation}")
    t = _DOUBLE_NOTATION_RE.sub(r"\2", t)
    t = _TRUNCATED_RE.sub(" ", t)
    t = _ANNOTATION_RE.sub(" ", t)
    t = t.replace("+", "")
    t = _SPACE_RE.sub(" ", t).strip()
    t = re.sub(r"\s+([,.?!:;])", r"\1", t)
    if not re.search(r"\w", t):
        return None, "no_words_after_cleaning"
    return t, "ok"


def shuffle_buffer(items: Iterable, buffer_size: int, seed: int) -> Iterator:
    """Strømmende stokking: holder ``buffer_size`` elementer og trekker
    tilfeldig. Deterministisk for gitt frø. ``buffer_size <= 1`` gir
    uendret rekkefølge."""
    if buffer_size <= 1:
        yield from items
        return
    rng = random.Random(seed)
    buf = []
    for x in items:
        buf.append(x)
        if len(buf) >= buffer_size:
            i = rng.randrange(len(buf))
            buf[i], buf[-1] = buf[-1], buf[i]
            yield buf.pop()
    rng.shuffle(buf)
    yield from buf


def strip_decoder_start(label_ids: list[int], decoder_start_token_id: int) -> list[int]:
    """Whisper legger selv til start-tokenet når etiketter forskyves. Står det
    også først i etiketten, lærer modellen et dobbelt start-token."""
    if label_ids and label_ids[0] == decoder_start_token_id:
        return label_ids[1:]
    return label_ids


def group_bucket(key: str, buckets: int = 1000) -> int:
    """Stabil bøtte 0..buckets-1 for en gruppe (taler, opptak)."""
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % buckets


def validate_out_dir(out_dir: str) -> str:
    """Stopper kjente feil der en PowerShell-variabel blir sendt inn som tekst
    (utdatamappen het «True» i en tidligere kjøring)."""
    if out_dir.strip().lower() in {"true", "false", "", "$true", "$false", "none", "null"}:
        raise ValueError(f"Ugyldig --out_dir: {out_dir!r}. Sjekk at variabelen i skriptet faktisk er en sti.")
    return out_dir
