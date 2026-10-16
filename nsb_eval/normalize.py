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
- tall gjøres entydige som sifre på begge sider: tallord, også sammensatte
  («totusenogseksten»), gammel tellemåte («femogtjue»), årstall
  («nittenåttiåtte») og klokkeslett («tjueen null null» = «21.00»)
- tegnsetting fjernes, bindestrek blir mellomrom
- aksenter fjernes, unntatt æ, ø og å

Normaliseringen gjør ikke om mellom bokmål og nynorsk, og den slår ikke sammen
radikale og konservative bokmålsformer (for eksempel «boka»/«boken»). Slike
forskjeller teller som feil og beskrives i metodedokumentet.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["FILLERS", "PROFILES", "normalize", "number_to_words", "ordinal_to_words"]

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
        tail = _below_thousand(rest)
        if 100 <= rest < 200:
            tail = "ett " + tail  # to tusen ett hundre
        return head + joiner + tail
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


# «13.» rett før et ord (ordenstall). Desimaltall og tusenskilletegn
# håndteres før dette.
_ORDINAL_RE = re.compile(r"\b(\d{1,3})\.(?=\s+[a-zæøå])")
_DECIMAL_RE = re.compile(r"\b(\d+),(\d+)\b")
# Klokkeslett «21.00» / «21:30» (timer 0–23, to sifre for minutter), men ikke
# datoer som «17.05.2018».
_CLOCK_RE = re.compile(r"(?<![\d.])\b([01]?\d|2[0-3])[.:]([0-5]\d)\b(?![.:]\d)")
_THOUSANDS_RE = re.compile(r"\b(\d{1,3})(?:[ . ](\d{3}))+\b")
_PERCENT_RE = re.compile(r"(\d)\s*%")
_PARAGRAPH_RE = re.compile(r"§+")
# Vanlige forkortelser i offentlig tale. Utvides på begge sider, slik at
# «1 mrd kr» og «en milliard kroner» blir like. Bare entydige forkortelser.
_ABBREVIATIONS = {
    "mrd": "milliarder", "mill": "millioner", "mio": "millioner", "pst": "prosent",
    "kr": "kroner", "nr": "nummer", "jf": "jamfør", "jfr": "jamfør", "mv": "med videre",
    "prop": "proposisjon", "innst": "innstilling", "km": "kilometer", "kg": "kilo",
}
_ABBREV_RE = re.compile(r"\b(" + "|".join(sorted(_ABBREVIATIONS, key=len, reverse=True)) + r")\b\.?")
_LEADING_ZERO_RE = re.compile(r"\b0\d+\b")
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _digits(group: str) -> str:
    """«00» -> «0 0», «05» -> «0 5»: slik sies tall med nuller foran."""
    return " ".join(group)


def _clock(m: re.Match) -> str:
    """Klokkeslett i samme form som når det sies med ord: «21.00» = «tjueen
    null null» -> «21 0 0»; «12.30» = «tolv tretti» -> «1230»; «9.30» =
    «ni tretti» -> «9 30»."""
    hour, minute = int(m.group(1)), m.group(2)
    if minute == "00":
        return f" {hour} 0 0 "
    if hour >= 10:
        return f" {hour}{minute} "
    return f" {hour} {int(minute)} "


def _expand_digits(text: str) -> str:
    """Gjør skrevne tall entydige. Tall beholdes som sifre; tallord gjøres om
    til sifre etterpå (``_words_to_digits``), slik at «2016» og
    «totusenogseksten» blir like."""
    text = _CLOCK_RE.sub(_clock, text)
    text = _PERCENT_RE.sub(r"\1 prosent", text)
    text = _PARAGRAPH_RE.sub(" paragraf ", text)
    text = _THOUSANDS_RE.sub(lambda m: re.sub(r"[ . ]", "", m.group(0)), text)
    text = _DECIMAL_RE.sub(lambda m: f" {int(m.group(1))} komma {_digits(m.group(2))} ", text)
    return _LEADING_ZERO_RE.sub(lambda m: _digits(m.group(0)), text)


# Tallord (bokmål og nynorsk) -> verdi og type.
_UNIT_WORDS = {
    "null": 0, "en": 1, "ett": 1, "ein": 1, "eitt": 1, "to": 2, "tre": 3, "fire": 4,
    "fem": 5, "seks": 6, "sju": 7, "syv": 7, "åtte": 8, "ni": 9,
}
_TEEN_WORDS = {
    "ti": 10, "elleve": 11, "tolv": 12, "tretten": 13, "fjorten": 14, "femten": 15,
    "seksten": 16, "sytten": 17, "atten": 18, "nitten": 19,
}
_TENS_WORDS = {
    "tjue": 20, "tyve": 20, "tretti": 30, "tredve": 30, "førti": 40, "femti": 50,
    "seksti": 60, "sytti": 70, "åtti": 80, "nitti": 90,
}
_MULT_WORDS = {
    "hundre": 100, "tusen": 1000, "million": 10**6, "millioner": 10**6, "millionar": 10**6,
    "milliard": 10**9, "milliarder": 10**9, "milliardar": 10**9,
}
_MORPHEMES = (
    [(w, "unit", v) for w, v in _UNIT_WORDS.items()]
    + [(w, "teen", v) for w, v in _TEEN_WORDS.items()]
    + [(w, "tens", v) for w, v in _TENS_WORDS.items()]
    + [(w, "mult", v) for w, v in _MULT_WORDS.items()]
    + [("og", "og", 0)]
)
_MORPHEMES.sort(key=lambda m: -len(m[0]))


def _split_morphemes(token: str) -> list[tuple[str, int]] | None:
    """Deler «totusenogseksten» i tallmorfemer, eller gir None."""
    best: dict[int, list] = {0: []}
    for i in range(len(token)):
        if i not in best:
            continue
        for word, kind, value in _MORPHEMES:
            if token.startswith(word, i) and i + len(word) not in best:
                best[i + len(word)] = best[i] + [(kind, value)]
    parts = best.get(len(token))
    if not parts or all(k == "og" for k, _ in parts):
        return None
    if parts[0][0] == "og" or parts[-1][0] == "og":
        return None
    if len(parts) > 1 and len(_evaluate(parts)) != 1:
        return None  # «tito» er ikke ett tall, og regnes som et vanlig ord
    return parts


def _evaluate(parts: list[tuple[str, int]]) -> list[str]:
    """Regner ut tallene i en sekvens av morfemer. Gir sifre, og «og» der
    ordet ikke var en del av et tall («to og to» -> «2 og 2»)."""
    out: list[str] = []
    total = cur = 0
    have = False
    last = None
    used_mult = False
    unit_after_mult = False  # siste ener ble lagt til rett etter hundre/tusen
    pending_og = False

    def flush():
        nonlocal total, cur, have, last, used_mult, unit_after_mult
        if have:
            out.append(str(total + cur))
        total = cur = 0
        have = False
        last = None
        used_mult = False
        unit_after_mult = False

    for kind, value in parts:
        if kind == "og":
            pending_og = True
            continue
        if kind == "num":  # et tall skrevet med sifre, f.eks. «2» i «2 millioner»
            flush()
            if pending_og:
                out.append("og")
            cur, have, last, pending_og = value, True, "num", False
            continue
        if kind == "mult":
            if not have:
                cur, have = 0, True
            if value == 100:
                cur = (cur or 1) * 100
            else:
                total += (cur or 1) * value
                cur = 0
            used_mult = True
            last = "mult"
            pending_og = False
            continue
        # unit, teen eller tens
        combine = False
        was_after_mult = False
        if have:
            small = cur % 100
            if last == "tens" and kind == "unit" and value < 10 and value > 0 and small % 10 == 0 and not pending_og:
                cur += value  # tjue + en
                combine = True
            elif (
                last == "unit" and kind == "tens" and pending_og and 0 < small < 10
                and (not used_mult or unit_after_mult)
            ):
                cur += value  # fem og tjue; hundre og enogsytti; to tusen og femogtjue
                combine = True
            elif last == "mult" and small == 0 and cur % 1000 < 1000:
                cur += value  # hundre (og) fem, tusen (og) tjue
                combine = True
                was_after_mult = kind == "unit"
            elif (
                not pending_og and not used_mult and total == 0 and 10 <= cur <= 99
                and kind in ("teen", "tens")
            ):
                cur = cur * 100 + value  # årstall: nitten åttiåtte, tjue sytten
                used_mult = True
                combine = True
                last = kind
                pending_og = False
                continue
        if not combine:
            flush()
            if pending_og:
                out.append("og")
            cur, have = value, True
        unit_after_mult = was_after_mult
        last = kind
        pending_og = False
    flush()
    if pending_og:
        out.append("og")
    return out


def _words_to_digits(tokens: list[str]) -> list[str]:
    """Erstatter løp av tallord med sifre. «og» tas bare med mellom tallord."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        parts = _split_morphemes(tokens[i]) if not tokens[i].isdigit() else None
        if parts is None and tokens[i].isdigit() and i + 1 < n:
            nxt = _split_morphemes(tokens[i + 1])
            if nxt and nxt[0][0] == "mult":
                parts = [("num", int(tokens[i]))]  # «2 millioner» = «to millioner»
        if parts is None:
            out.append(tokens[i])
            i += 1
            continue
        run = list(parts)
        j = i + 1
        while j < n:
            if tokens[j] == "og" and j + 1 < n and _split_morphemes(tokens[j + 1]) is not None:
                run.append(("og", 0))
                run.extend(_split_morphemes(tokens[j + 1]))
                j += 2
                continue
            nxt = _split_morphemes(tokens[j]) if tokens[j] != "og" else None
            if nxt is None:
                break
            run.extend(nxt)
            j += 1
        out.extend(_evaluate(run))
        i = j
    return out


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


PROFILES = ("lesbar", "ordrett")

# Annotasjoner som betyr at taleren nølte (fyllord). I ordrett profil blir de
# til «eh», slik at et fyllord modellen skriver kan telles som riktig.
# NPSC: <ee>, <mm>. NB Samtale: %eee, %emm, %mmm. Latter (%heh) og smatting (%ttt) er ikke ord.
_FILLER_ANNOTATION_RE = re.compile(r"<(?:e+|eh|ehm|m+|hm+)>|%(?:e+|eh|ehm|em+|m+|hm+)\b", flags=re.IGNORECASE)
_FILLER_TOKEN = "eh"


def normalize(text: str | None, profile: str = "lesbar") -> str:
    """Normaliserer en transkripsjon for WER/CER-beregning.

    ``lesbar`` (standard): fyllord og avbrutte ord fjernes. Måler om teksten
    gir riktig innhold.

    ``ordrett``: fyllord (også annoterte, som ``<ee>`` og ``%eee``) blir til
    «eh», og avbrutte ord («ble£») beholdes uten merket. Måler om alt som ble
    sagt, står i teksten, slik ordrett gjengivelse i retten krever. Ellers lik
    ``lesbar``.
    """
    if profile not in PROFILES:
        raise ValueError(f"Ukjent profil {profile!r}; bruk en av {PROFILES}")
    if not text:
        return ""
    verbatim = profile == "ordrett"
    t = unicodedata.normalize("NFC", text)
    t = _DOUBLE_NOTATION_RE.sub(r"\2", t)
    if verbatim:
        t = t.replace("£", " ")
        t = _FILLER_ANNOTATION_RE.sub(f" {_FILLER_TOKEN} ", t)
    else:
        t = _TRUNCATED_RE.sub(" ", t)
    t = _ANNOTATION_RE.sub(" ", t)
    # Ordenstall før små bokstaver: «13. februar», men ikke «kom 3. Så».
    t = _ORDINAL_RE.sub(lambda m: ordinal_to_words(int(m.group(1))), t)
    t = t.lower()
    t = _ABBREV_RE.sub(lambda m: " " + _ABBREVIATIONS[m.group(1)] + " ", t)
    t = _expand_digits(t)
    t = t.replace("-", " ").replace("_", " ")
    t = _PUNCT_RE.sub(" ", t)
    t = _strip_accents(t)
    if verbatim:
        words = [_FILLER_TOKEN if w in FILLERS else w for w in _SPACE_RE.split(t) if w]
    else:
        words = [w for w in _SPACE_RE.split(t) if w and w not in FILLERS]
    return " ".join(_words_to_digits(words))
