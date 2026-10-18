import pytest

from nsb_engine.legal_format import FormatOptions, format_legal

NB = " "


@pytest.mark.parametrize(
    "spoken, written",
    [
        ("straffeloven paragraf to hundre og syttien første ledd", f"straffeloven §{NB}271 første ledd"),
        ("Straffeloven paragraf 271 første ledd annet punktum", f"Straffeloven §{NB}271 første ledd annet punktum"),
        ("paragrafene to hundre og sytti og to hundre og syttien", f"§§{NB}270 og 271"),
        ("jf. paragraf 5 annet ledd", f"jf. §{NB}5 annet ledd"),
        ("se kapittel tre", "se kapittel 3"),
        ("tolvte mars totusenogtjuefem", "12. mars 2025"),
        ("den 3 april 2024 møtte han", "den 3. april 2024 møtte han"),
        ("den første juni", "den 1. juni"),
        ("en komma fem millioner kroner", "1,5 millioner kroner"),
        ("renten var tre komma fem prosent", "renten var 3,5 prosent"),
        ("beløpet var femten tusen kroner", f"beløpet var 15{NB}000 kroner"),
        ("en bot på fem tusen kroner", "en bot på 5000 kroner"),
        ("to hundre og femti tusen kroner", f"250{NB}000 kroner"),
        ("klokka fjorten tretti", "kl. 14.30"),
        ("klokken ni", "kl. 9"),
        ("sak tjuefire bindestrek en to tre fire fem seks MED-OTIR", "sak 24-123456MED-OTIR"),
        ("han var tjuefem år", "han var 25 år"),
        ("i totusenogtjueen flyttet han", "i 2021 flyttet han"),
        ("det skjedde i to tusen og tjue", "det skjedde i 2020"),
    ],
)
def test_legal_formatting(spoken, written):
    assert format_legal(spoken) == written


@pytest.mark.parametrize(
    "text",
    [
        "to vitner så det",  # små tall uten juridisk sammenheng står med ord
        "en mann kom inn",
        "tusen takk for det",
        "han kom for andre gang",
        "første ledd annet punktum gjelder",  # henvisning, ikke kommando
        "retten satte punktum for saken",
        "Det står et komma for mye",
    ],
)
def test_left_alone(text):
    assert format_legal(text) == text


def test_dictation_commands():
    assert format_legal("han nektet punktum nytt avsnitt vitnet forklarte at") == "han nektet.\n\nVitnet forklarte at"
    assert format_legal("visste han det spørsmålstegn") == "visste han det?"
    assert format_legal("han kom ikke, punktum.") == "han kom ikke."
    assert format_legal("tiltalte komma født i 1980 komma erkjente") == "tiltalte, født i 1980, erkjente"
    assert format_legal("første linje ny linje andre linje") == "første linje\nAndre linje"


def test_options_turn_rules_off():
    off = FormatOptions(commands=False, paragraphs=False)
    assert format_legal("paragraf 5 punktum", off) == "paragraf 5 punktum"


def test_already_written_text_is_unchanged():
    text = f"Etter straffeloven §{NB}271 første ledd, jf. §{NB}79, kl. 14.30 den 12. mars 2025."
    assert format_legal(text) == text
