"""Tekstnormalisering for norsk talegjenkjenning.

Målet er å sammenligne det som ble *sagt*, ikke skrivemåte. Normaliseringen
er den samme for fasit og modellsvar, og den er bevisst konservativ:

- små bokstaver, Unicode NFC
- NB Samtales dobbeltnotasjon ``muntlig\\skriftlig`` (``dokker\\dere``,
  ``N_R_K\\NRK``) erstattes med den skriftlige formen etter skråstreken
- avbrutte ord merket med ``£`` (``ble£``) fjernes
- annotasjoner fjernes: NPSC (``<ee>``, ``<INAUDIBLE>`` ...), NB Samtale
  (``%eee``, ``%unint`` ...) og klammeparenteser
- fyllord (``eh``, ``ehm``, ``mm`` ...) fjernes, fordi NPSC og NB Samtale
  markerer dem som annotasjoner og modeller skriver dem ulikt
- tall skrevet med sifre gjøres om til ord (bokmål, moderne tellemåte), slik
  at «21» og «tjueen» regnes som like
- tegnsetting fjernes, bindestrek blir mellomrom
- aksenter fjernes, unntatt æ, ø og å

Normaliseringen gjør ikke om mellom bokmål og nynorsk, og den slår ikke sammen
radikale og konservative bokmålsformer (for eksempel «boka»/«boken»). Slike
forskjeller teller som feil og beskrives i metodedokumentet.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["FILLERS", "normalize", "number_to_words", "ordinal_to_words"]

# Annotasjoner i fasitene. Fjernes helt.
_ANNOTATION_RE = re.compile(
    r"<[^>]*>"  # NPSC: <ee>, <mm>, <qq>, <INAUDIBLE>
    r"|%\w+"  # NB Samtale: %eee, %unint, %overlapping, %foreign
    r"|\[[^\]]*\]"  # [uhørbart], [latter]
    r"|\{[^}]*\}"
)

# NB Samtale: «dokker\dere» = sagt\skriftlig. Vi beholder skriftlig form.
_DOUBLE_NOTATION_RE = re.compile(r"(\S+)\\(\S+)")
# NB Samtale: avbrutt ord, «ble£».
_TRUNCATED_RE = re.compile(r"\S*£")

# Fyllord som modeller ofte skriver ut, men som fasitene markerer som
# annotasjoner. Fjernes i både fasit og svar.
FILLERS = frozenset(
    {
        "eh", "ehm", "eee", "ee", "æh", "æhm", "øh", "øhm", "hm", "hmm", "mm",
        "mmm", "m", "em", "emm", "eem", "heh", "uh", "um", "ah", "aah",
    }
)

_ONES = [
    "null", "en", "to", "tre", "fire", "fem", "seks", "sju", "åtte", "ni",
    "ti", "elleve", "tolv", "tretten", "fjorten", "femten", "seksten",
    "sytten", "atten", "nitten",
]
_TENS = {
    2: "tjue", 3: "tretti", 4: "førti", 5: "femti",
    6: "seksti", 7: "sytti", 8: "åtti", 9: "nitti",
}
_ORDINAL_SMALL = {
    1: "første", 2: "andre", 3: "tredje", 4: "fjerde", 5: "femte",
    6: "sjette", 7: "sjuende", 8: "åttende", 9: "niende", 10: "tiende",
    11: "ellevte", 12: "tolvte",
}


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (_ONES[ones] if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append("hundre" if hundreds == 1 else f"{_ONES[hundreds]} hundre")
    if rest:
        if hundreds:
            parts.append("og")
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """Grunntall på bokmål med moderne tellemåte (21 -> «tjueen»).

    Tall fra 1100 til 1999 leses som årstall («nitten hundre og nittini»),
    slik de vanligvis sies og transkriberes. Tall over 999 999 999 returneres
    som sifre.
    """
    if n < 0:
        return "minus " + number_to_words(-n)
    if n < 100:
        return _below_hundred(n)
    if n < 1000:
        return _below_thousand(n)
    if 1100 <= n <= 1999 and n % 100 != 0:
        hundreds, rest = divmod(n, 100)
        return f"{_below_hundred(hundreds)} hundre og {_below_hundred(rest)}"
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = "tusen" if thousands == 1 else f"{_below_thousand(thousands)} tusen"
        if not rest:
            return head
        joiner = " og " if rest < 100 else " "
        return head + joiner + _below_thousand(rest)
    if n < 1_000_000_000:
        millions, rest = divmod(n, 1_000_000)
        head = "en million" if millions == 1 else f"{_below_thousand(millions)} millioner"
        if not rest:
            return head
        joiner = " og " if rest < 100 else " "
        return head + joiner + number_to_words(rest)
    return str(n)


def ordinal_to_words(n: int) -> str:
    """Ordenstall på bokmål (13 -> «trettende», 21 -> «tjueførste»)."""
    if n in _ORDINAL_SMALL:
        return _ORDINAL_SMALL[n]
    if n < 20:
        return _ONES[n] + "de"
    if n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return _TENS[tens].removesuffix("e") + "ende"  # tjuende, trettiende
        return _TENS[tens] + _ORDINAL_SMALL.get(ones, _ONES[ones] + "de")
    return number_to_words(n) + "ende"


# «13.» rett før et ord (ordenstall) eller et heltall. Desimaltall og
# tusenskilletegn håndteres før dette.
_ORDINAL_RE = re.compile(r"\b(\d{1,3})\.(?=\s+[a-zæøå])")
_DECIMAL_RE = re.compile(r"\b(\d+),(\d+)\b")
# Klokkeslett «21.00» / «21:30» (timer 0–23, to sifre for minutter).
_CLOCK_RE = re.compile(r"\b([01]?\d|2[0-3])[.:]([0-5]\d)\b")
_THOUSANDS_RE = re.compile(r"\b(\d{1,3})(?:[ . ](\d{3}))+\b")
_PERCENT_RE = re.compile(r"(\d)\s*%")
_PARAGRAPH_RE = re.compile(r"§+")
_INT_RE = re.compile(r"\d+")
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _clock(m: re.Match) -> str:
    hour, minute = int(m.group(1)), m.group(2)
    tail = "null null" if minute == "00" else number_to_words(int(minute))
    return f" {number_to_words(hour)} {tail} "


def _expand_numbers(text: str) -> str:
    text = _CLOCK_RE.sub(_clock, text)
    text = _PERCENT_RE.sub(r"\1 prosent", text)
    text = _PARAGRAPH_RE.sub(" paragraf ", text)
    text = _THOUSANDS_RE.sub(lambda m: m.group(0).replace(" ", "").replace(".", "").replace(" ", ""), text)
    text = _DECIMAL_RE.sub(
        lambda m: f"{number_to_words(int(m.group(1)))} komma {' '.join(_ONES[int(d)] for d in m.group(2))}",
        text,
    )
    text = _ORDINAL_RE.sub(lambda m: ordinal_to_words(int(m.group(1))), text)
    return _INT_RE.sub(lambda m: f" {number_to_words(int(m.group(0)))} ", text)


def _strip_accents(text: str) -> str:
    """Fjerner aksenter (é -> e), men beholder æ, ø og å."""
    out = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":
            # Behold ringen i å (a + U+030A).
            if ch == "̊" and out and out[-1] in "aA":
                out.append(ch)
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def normalize(text: str | None) -> str:
    """Normaliserer en transkripsjon for WER/CER-beregning."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = _DOUBLE_NOTATION_RE.sub(r"\2", t)
    t = _TRUNCATED_RE.sub(" ", t)
    t = _ANNOTATION_RE.sub(" ", t)
    t = t.lower()
    t = _expand_numbers(t)
    t = t.replace("-", " ").replace("_", " ")
    t = _PUNCT_RE.sub(" ", t)
    t = _strip_accents(t)
    words = [w for w in _SPACE_RE.split(t) if w and w not in FILLERS]
    return " ".join(words)
