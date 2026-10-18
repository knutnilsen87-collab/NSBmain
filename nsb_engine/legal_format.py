"""Skriver diktert juridisk tekst slik den skal stå i et dokument.

Gjenkjenningen gir tekst slik den ble sagt. Advokaten vil ha den slik den
skrives:

    «straffeloven paragraf to hundre og syttien første ledd»
        -> «straffeloven § 271 første ledd»
    «tolvte mars totusenogtjuefem»          -> «12. mars 2025»
    «en komma fem millioner kroner»         -> «1,5 millioner kroner»
    «klokka fjorten tretti»                 -> «kl. 14.30»
    «sak tjuefire bindestrek en to tre fire fem seks» -> «sak 24-123456»
    «han nektet punktum nytt avsnitt»       -> «han nektet.\\n\\n»

Regler:

- Tallord blir sifre i juridiske sammenhenger (paragraf, kapittel, artikkel,
  nummer, sak, side, klokkeslett, datoer, beløp, prosent) og ellers når tallet
  er 13 eller høyere. «To vitner» forblir «to vitner».
- Ledd, punktum og bokstav står med ord («første ledd annet punktum»), slik
  det er vanlig i norsk juridisk tekst.
- Dikteringskommandoer (punktum, komma, kolon, spørsmålstegn, ny linje, nytt
  avsnitt) blir tegn. «Første punktum» er en henvisning, ikke en kommando.

Funksjonen endrer bare det den kjenner igjen, og lar resten stå uendret.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nsb_eval.normalize import _split_morphemes, _words_to_digits, ordinal_to_words

__all__ = ["format_legal", "FormatOptions"]


@dataclass(frozen=True)
class FormatOptions:
    numbers: bool = True  # tallord til sifre etter reglene over
    paragraphs: bool = True  # «paragraf 271» -> «§ 271»
    dates: bool = True
    clock: bool = True
    case_numbers: bool = True
    commands: bool = True  # dikteringskommandoer
    digits_from: int = 13  # tall fra og med denne verdien skrives med sifre uten juridisk sammenheng


_TOKEN_RE = re.compile(r"\n+|[^\S\n]+|\w+(?:[-'’]\w+)*|[^\w\s]", re.UNICODE)

_MONTHS = (
    "januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
    "september", "oktober", "november", "desember",
)
_ORDINALS = {ordinal_to_words(n): n for n in range(1, 32)}
_ORDINALS.update({"annen": 2, "annet": 2, "sjuende": 7, "syvende": 7, "tjuende": 20, "trettiende": 30})
_REFERENCE_ORDINALS = set(_ORDINALS) | {"siste", "nest", "nestsiste", "samme"}

# Ord foran et tall som gjør at tallet skal stå med sifre.
_BEFORE = {
    "kapittel", "kapitlet", "kap", "artikkel", "artiklene", "art", "nr", "nummer", "sak", "saksnummer",
    "side", "sidene", "s", "bilag", "dokument", "dok", "punkt", "post", "rom", "versjon", "år", "året",
    "i", "fra", "til", "siden", "innen", "før", "etter", "per", "pr",
}
# «i», «fra», «til» osv. gir bare sifre for årstall-lignende verdier (se _needs_digits).
_YEAR_ONLY_BEFORE = {"i", "fra", "til", "siden", "innen", "før", "etter", "år", "året"}
_AFTER = {
    "kroner", "kr", "krone", "øre", "euro", "dollar", "prosent", "promille", "kilo", "kg", "gram", "meter",
    "km", "kilometer", "millioner", "million", "milliarder", "milliard", "mill", "mrd", "km/t",
}
_LARGE_WORDS = {"million", "millioner", "millionar", "milliard", "milliarder", "milliardar"}
_PARAGRAPH_WORDS = {"paragraf": "§", "paragrafen": "§", "paragrafene": "§§", "paragrafer": "§§"}
_CLOCK_WORDS = {"klokka", "klokken", "kl"}
_HYPHEN_WORDS = {"bindestrek", "strek"}
_CASE_CODE_RE = re.compile(r"^[A-ZÆØÅ]{3}-[A-ZÆØÅ]{4}$")

# «satte punktum for saken», «et komma»: ordet brukes, ikke dikteres.
_NOT_COMMAND_AFTER = {"sette", "satte", "setter", "satt", "settes", "et", "eit", "ett", "ordet", "nytt", "eget"}
_COMMANDS_1 = {"punktum": ".", "komma": ",", "kolon": ":", "semikolon": ";", "spørsmålstegn": "?", "utropstegn": "!"}
_COMMANDS_2 = {("ny", "linje"): "\n", ("nytt", "avsnitt"): "\n\n", ("ny", "linje."): "\n"}


@dataclass
class _Tok:
    text: str
    kind: str  # "w" ord, "s" mellomrom, "n" linjeskift, "p" tegn

    @property
    def low(self) -> str:
        return self.text.lower()


def _tokenize(text: str) -> list[_Tok]:
    out = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        if t.startswith("\n"):
            kind = "n"
        elif t.isspace():
            kind = "s"
        elif re.match(r"\w", t):
            kind = "w"
        else:
            kind = "p"
        out.append(_Tok(t, kind))
    return out


def _is_number_word(low: str) -> bool:
    return low.isdigit() or _split_morphemes(low) is not None


def _words(toks: list[_Tok]) -> list[int]:
    return [i for i, t in enumerate(toks) if t.kind == "w"]


def _prev_word(toks: list[_Tok], i: int) -> int | None:
    j = i - 1
    while j >= 0 and toks[j].kind == "s":
        j -= 1
    return j if j >= 0 and toks[j].kind in ("w", "num") else None


def _next_word(toks: list[_Tok], i: int) -> int | None:
    j = i + 1
    while j < len(toks) and toks[j].kind == "s":
        j += 1
    return j if j < len(toks) and toks[j].kind in ("w", "num") else None


def _group_thousands(digits: str) -> str:
    if len(digits) <= 4:
        return digits  # 2025, 1500 (fire sifre skrives uten mellomrom)
    groups = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    return " ".join(groups)


def _needs_digits(value: int, before: str | None, after: str | None, opts: FormatOptions) -> bool:
    if before in _PARAGRAPH_WORDS or before == "§" or before in _CLOCK_WORDS:
        return True
    if after in _AFTER:
        return True
    if before in _BEFORE:
        if before in _YEAR_ONLY_BEFORE:
            return 1000 <= value <= 2100
        return True
    return value >= opts.digits_from


def _convert_numbers(toks: list[_Tok], opts: FormatOptions) -> list[_Tok]:
    """Finner løp av tallord (med mellomrom og «og» mellom) og skriver dem
    som sifre der reglene sier det."""
    out: list[_Tok] = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t.kind != "w" or t.low.isdigit() or not _is_number_word(t.low) or t.low == "og":
            out.append(t)
            i += 1
            continue
        # Samle løpet: tallord, mellomrom, «og» mellom tallord.
        j = i
        run_idx = []
        while j < n:
            if toks[j].kind == "w" and _is_number_word(toks[j].low) and not toks[j].low.isdigit():
                run_idx.append(j)
                j += 1
            elif toks[j].kind == "s":
                j += 1
            elif toks[j].kind == "w" and toks[j].low == "og":
                k = _next_word(toks, j)
                if k is not None and _is_number_word(toks[k].low) and not toks[k].low.isdigit():
                    run_idx.append(j)
                    j += 1
                else:
                    break
            else:
                break
        # «fem millioner kroner» skrives «5 millioner kroner»: et avsluttende
        # million/milliard blir stående som ord.
        while len(run_idx) > 1 and toks[run_idx[-1]].low in _LARGE_WORDS:
            run_idx.pop()
        while run_idx and toks[run_idx[-1]].low == "og":
            run_idx.pop()
        if not run_idx or toks[run_idx[0]].low in _LARGE_WORDS:
            out.append(t)
            i += 1
            continue
        end = run_idx[-1] + 1
        words = [toks[k].low for k in run_idx]
        values = _words_to_digits(words)
        prev = _prev_word(toks, i)
        before = toks[prev].low if prev is not None else None
        if before is None and i > 0 and toks[i - 1].kind == "s" and i > 1 and toks[i - 2].text == "§":
            before = "§"
        nxt = _next_word(toks, end - 1)
        after = toks[nxt].low if nxt is not None else None
        if after == "komma":
            k2 = _next_word(toks, nxt)
            if k2 is not None and _is_number_word(toks[k2].low):
                after = "kroner"  # desimaltall: heltallsdelen skrives alltid med sifre
        numeric = [v for v in values if v != "og"]
        lone_mult = len(run_idx) == 1 and words[0] in ("hundre", "tusen")
        if lone_mult and not (before in _PARAGRAPH_WORDS or after in _AFTER or before in _BEFORE - _YEAR_ONLY_BEFORE):
            out.extend(toks[i:end])  # «tusen takk»
            i = end
            continue
        if len(numeric) == 1 and len(values) == 1:
            value = int(numeric[0])
            month_next = after in _MONTHS
            if _needs_digits(value, before, after, opts) and not month_next:
                out.append(_Tok(_group_thousands(numeric[0]) if after in _AFTER else numeric[0], "num"))
            else:
                out.extend(toks[i:end])
        elif len(numeric) >= 1:
            # Flere tall etter hverandre («to og to», «én to tre»): sifre bare i juridisk sammenheng.
            big = all(int(v) >= opts.digits_from for v in numeric)
            legal = before in _PARAGRAPH_WORDS or before in _BEFORE - _YEAR_ONLY_BEFORE or before in _CLOCK_WORDS \
                or before in _HYPHEN_WORDS or after in _HYPHEN_WORDS or before == "§"
            if big or legal:
                for k, v in enumerate(values):
                    if k:
                        out.append(_Tok(" ", "s"))
                    out.append(_Tok(v, "num" if v != "og" else "w"))
            else:
                out.extend(toks[i:end])
        else:
            out.extend(toks[i:end])
        i = end
    return out


def _is_num(t: _Tok) -> bool:
    return t.kind == "num" or (t.kind == "w" and t.text.replace(" ", "").isdigit())


def _num_value(t: _Tok) -> int:
    return int(t.text.replace(" ", ""))


def _decimals(toks: list[_Tok]) -> list[_Tok]:
    """«1 komma 5» -> «1,5». Desimaldelen er ett tall eller tallord."""
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "w" and t.low == "komma" and out:
            p = len(out) - 1
            while p >= 0 and out[p].kind == "s":
                p -= 1
            k = _next_word(toks, i)
            if p >= 0 and _is_num(out[p]) and k is not None and k == i + 2:
                low = toks[k].low.replace("\u00a0", "")
                dec = low if low.isdigit() else None
                if dec is None and _split_morphemes(low) is not None:
                    vals = _words_to_digits([low])
                    dec = vals[0] if len(vals) == 1 else None
                if dec is not None:
                    del out[p + 1:]
                    out[p] = _Tok(out[p].text.replace("\u00a0", "") + "," + dec, "num")
                    i = k + 1
                    continue
        out.append(t)
        i += 1
    return out


def _paragraphs(toks: list[_Tok]) -> list[_Tok]:
    out: list[_Tok] = []
    for i, t in enumerate(toks):
        if t.kind == "w" and t.low in _PARAGRAPH_WORDS:
            k = _next_word(toks, i)
            nxt = toks[k] if k is not None else (toks[i + 2] if i + 2 < len(toks) else None)
            if nxt is not None and (_is_num(nxt) or nxt.kind == "num"):
                out.append(_Tok(_PARAGRAPH_WORDS[t.low], "p"))
                continue
        out.append(t)
    # «§ 271» skal ha hardt mellomrom
    for i in range(len(out) - 2):
        if out[i].text in ("§", "§§") and out[i + 1].kind == "s" and _is_num(out[i + 2]):
            out[i + 1] = _Tok(" ", "s")
    return out


def _dates(toks: list[_Tok]) -> list[_Tok]:
    """«tolvte mars» -> «12. mars»; årstall etter måned blir sifre."""
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "w" and t.low in _ORDINALS:
            k = _next_word(toks, i)
            if k is not None and toks[k].low in _MONTHS:
                out.append(_Tok(f"{_ORDINALS[t.low]}.", "num"))
                out.extend(toks[i + 1:k + 1])
                i = k + 1
                continue
        if t.kind in ("num", "w") and _is_num(t) and 1 <= _num_value(t) <= 31:
            k = _next_word(toks, i)
            if k is not None and toks[k].low in _MONTHS and (i + 1 < len(toks) and toks[i + 1].text != "."):
                out.append(_Tok(f"{_num_value(t)}.", "num"))
                out.extend(toks[i + 1:k + 1])
                i = k + 1
                continue
        out.append(t)
        i += 1
    # Årstall etter måned: «mars totusenogtjuefem» -> «mars 2025»
    res: list[_Tok] = []
    i = 0
    while i < len(out):
        t = out[i]
        res.append(t)
        if t.kind == "w" and t.low in _MONTHS:
            k = _next_word(out, i)
            if k is not None and not out[k].low.isdigit():
                # samle tallordløp
                j = k
                words = []
                while j is not None and _split_morphemes(out[j].low) is not None:
                    words.append(out[j].low)
                    nj = _next_word(out, j)
                    if nj is None:
                        j += 1
                        break
                    j = nj
                if words:
                    vals = _words_to_digits(words)
                    if len(vals) == 1 and 1000 <= int(vals[0]) <= 2100:
                        res.extend(out[i + 1:k])
                        res.append(_Tok(vals[0], "num"))
                        i = (j if j is not None else len(out))
                        # j peker på første ord etter årstallet; ta med mellomrom foran det
                        if i < len(out) and out[i].kind == "w" and out[i - 1].kind == "s":
                            i -= 1
                        continue
        i += 1
    return res


def _clock(toks: list[_Tok]) -> list[_Tok]:
    """«klokka 14 30» / «klokka 1430» -> «kl. 14.30»; «klokka 9» -> «kl. 9»."""
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "w" and t.low in _CLOCK_WORDS:
            k = _next_word(toks, i)
            # «kl.» med punktum fra modellen
            if k is None and i + 2 < len(toks) and toks[i + 1].text == ".":
                k = i + 3 if i + 3 < len(toks) and _is_num(toks[i + 3]) else None
            if k is not None and _is_num(toks[k]):
                hour_tok = toks[k]
                v = _num_value(hour_tok)
                text = None
                end = k + 1
                if 100 <= v <= 2359 and v % 100 < 60 and v // 100 <= 23:
                    text = f"{v // 100:02d}.{v % 100:02d}" if v // 100 >= 10 else f"{v // 100}.{v % 100:02d}"
                elif 0 <= v <= 24:
                    m = _next_word(toks, k)
                    if m is not None and _is_num(toks[m]) and 0 <= _num_value(toks[m]) < 60 and m == k + 2:
                        text = f"{v}.{_num_value(toks[m]):02d}"
                        end = m + 1
                    else:
                        text = str(v)
                if text:
                    out.append(_Tok("kl.", "w"))
                    out.append(_Tok(" ", "s"))
                    out.append(_Tok(text, "num"))
                    i = end
                    continue
        out.append(t)
        i += 1
    return out


def _case_numbers(toks: list[_Tok]) -> list[_Tok]:
    """«24 bindestrek 1 2 3 4 5 6» -> «24-123456»; henger på «MED-OTIR»."""
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "w" and t.low in _HYPHEN_WORDS:
            # venstre side: siste tall i out
            p = len(out) - 1
            while p >= 0 and out[p].kind == "s":
                p -= 1
            k = _next_word(toks, i)
            if p >= 0 and _is_num(out[p]) and k is not None and _is_num(toks[k]):
                digits = []
                j = k
                while j is not None and j < len(toks) and _is_num(toks[j]):
                    digits.append(toks[j].text.replace(" ", ""))
                    nj = _next_word(toks, j)
                    if nj is None or nj != j + 2:
                        j += 1
                        break
                    j = nj
                del out[p + 1:]
                out[p] = _Tok(out[p].text.replace(" ", "") + "-" + "".join(digits), "num")
                i = j
                # rettskode rett etter («MED-OTIR»)
                if i + 1 < len(toks) and toks[i].kind == "s" and _CASE_CODE_RE.match(toks[i + 1].text):
                    out[-1] = _Tok(out[-1].text + toks[i + 1].text, "num")
                    i += 2
                continue
        out.append(t)
        i += 1
    return out


def _commands(toks: list[_Tok]) -> list[_Tok]:
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "w":
            k = _next_word(toks, i)
            if k is not None and (t.low, toks[k].low) in _COMMANDS_2:
                _strip_trailing_space(out)
                out.append(_Tok(_COMMANDS_2[(t.low, toks[k].low)], "n"))
                i = _skip_after_command(toks, k + 1)
                continue
            if t.low in _COMMANDS_1:
                prev = _prev_word(toks, i)
                ref = prev is not None and (
                    (toks[prev].low in _REFERENCE_ORDINALS and t.low == "punktum") or toks[prev].low in _NOT_COMMAND_AFTER
                )
                decimal = t.low == "komma" and prev is not None and k is not None and \
                    _is_number_word(toks[prev].low) and _is_number_word(toks[k].low)
                if not ref and not decimal:
                    _strip_trailing_space(out)
                    # Modellen har kanskje satt sitt eget tegn foran: «nektet, punktum»
                    if out and out[-1].kind == "p" and out[-1].text in ",.":
                        out.pop()
                    out.append(_Tok(_COMMANDS_1[t.low], "p"))
                    i = _skip_after_command(toks, i + 1)
                    continue
        out.append(t)
        i += 1
    return out


def _strip_trailing_space(out: list[_Tok]) -> None:
    while out and out[-1].kind == "s":
        out.pop()


def _skip_after_command(toks: list[_Tok], i: int) -> int:
    """Hopper over tegn modellen selv satte etter kommandoordet («punktum.»)."""
    while i < len(toks) and toks[i].kind == "p" and toks[i].text in ".,":
        i += 1
    return i


def _capitalize_sentences(toks: list[_Tok]) -> list[_Tok]:
    cap = False
    for i, t in enumerate(toks):
        if t.kind in ("p",) and t.text in ".?!":
            cap = True
        elif t.kind == "n":
            cap = True
        elif t.kind == "w":
            if cap and t.text[:1].islower():
                toks[i] = _Tok(t.text[:1].upper() + t.text[1:], "w")
            cap = False
        elif t.kind == "num":
            cap = False
    return toks


def _join(toks: list[_Tok]) -> str:
    out = []
    for i, t in enumerate(toks):
        if t.kind == "s" and i + 1 < len(toks) and toks[i + 1].kind == "n":
            continue
        if t.kind == "s" and i > 0 and toks[i - 1].kind == "n":
            continue
        out.append(t.text)
    return "".join(out)


def format_legal(text: str, options: FormatOptions | None = None) -> str:
    """Formaterer diktert tekst. Se modulbeskrivelsen for reglene."""
    if not text:
        return text
    opts = options or FormatOptions()
    toks = _tokenize(text)
    command_used = False
    if opts.commands:
        before = len(toks)
        toks = _commands(toks)
        command_used = len(toks) != before or any(t.kind == "n" for t in toks)
    if opts.dates:
        toks = _dates(toks)
    if opts.numbers:
        toks = _convert_numbers(toks, opts)
        toks = _decimals(toks)
    if opts.clock:
        toks = _clock(toks)
    if opts.case_numbers:
        toks = _case_numbers(toks)
    if opts.paragraphs:
        toks = _paragraphs(toks)
    if command_used:
        toks = _capitalize_sentences(toks)
    return _join(toks)
