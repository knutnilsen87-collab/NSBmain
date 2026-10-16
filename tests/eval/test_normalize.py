import pytest

from nsb_eval.normalize import normalize, number_to_words, ordinal_to_words


@pytest.mark.parametrize(
    "n, words",
    [
        (0, "null"),
        (7, "sju"),
        (13, "tretten"),
        (20, "tjue"),
        (21, "tjueen"),
        (99, "nittini"),
        (100, "hundre"),
        (105, "hundre og fem"),
        (271, "to hundre og syttien"),
        (1000, "tusen"),
        (1001, "tusen og en"),
        (1500, "tusen fem hundre"),
        (1999, "nitten hundre og nittini"),
        (1905, "nitten hundre og fem"),
        (2000, "to tusen"),
        (2023, "to tusen og tjuetre"),
        (45000, "førtifem tusen"),
        (1_000_000, "en million"),
        (2_500_000, "to millioner fem hundre tusen"),
    ],
)
def test_number_to_words(n, words):
    assert number_to_words(n) == words


@pytest.mark.parametrize(
    "n, words",
    [(1, "første"), (2, "andre"), (3, "tredje"), (13, "trettende"), (20, "tjuende"), (21, "tjueførste"), (31, "trettiførste")],
)
def test_ordinal_to_words(n, words):
    assert ordinal_to_words(n) == words


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Stortingets møte er lovlig satt.", "stortingets møte er lovlig satt"),
        ("<ee> det er <INAUDIBLE> greit <qq>", "det er greit"),
        ("%eee så velkommen, %unint til alle", "så velkommen til alle"),
        ("eh ja, ehm, det er hmm greit", "ja det er greit"),
        ("det gjør det hyggelig å se at dokker\\dere er her", "det gjør det hyggelig å se at dere er her"),
        ("N_R_K-appen\\NRK-appen er s£ bra", "nrk appen er bra"),
        ("klokka 21.00 i kveld", "klokka tjueen null null i kveld"),
        ("klokka 9:30", "klokka ni tretti"),
        ("13. februar", "trettende februar"),
        ("straffeloven § 271", "straffeloven paragraf to hundre og syttien"),
        ("3,5 %", "tre komma fem prosent"),
        ("1 500 kroner", "tusen fem hundre kroner"),
        ("Kafé i Malmö", "kafe i malmo"),
        ("blåbær og ærfugl", "blåbær og ærfugl"),
        ("e-post", "e post"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_is_idempotent():
    s = "Det var 21 personer, %eee og dokker\\dere kom 13. mai."
    once = normalize(s)
    assert normalize(once) == once


def test_digits_and_words_compare_equal():
    assert normalize("Vi møtes 21.00") == normalize("vi møtes tjueen null null")
