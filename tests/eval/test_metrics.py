import random

import pytest

from nsb_eval.metrics import EditCounts, align_counts, char_counts, item_flags, repetition_loop, word_counts


def _reference_levenshtein(a, b):
    """Enkel referanseimplementasjon for å kontrollere totalen."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return d[-1][-1]


def test_identical():
    c = word_counts("en to tre", "en to tre")
    assert c.errors == 0 and c.reference_length == 3 and c.error_rate == 0.0


def test_substitution_deletion_insertion():
    c = word_counts("en to tre fire", "en tre fire fem")
    assert (c.substitutions, c.deletions, c.insertions) == (0, 1, 1)
    c = word_counts("en to tre", "en for tre")
    assert (c.substitutions, c.deletions, c.insertions) == (1, 0, 0)


def test_wer_can_exceed_one():
    c = word_counts("ja", "ja ja ja ja ja")
    assert c.insertions == 4 and c.error_rate == 4.0


def test_empty_reference():
    c = word_counts("", "noe tekst")
    assert c.insertions == 2 and c.error_rate == float("inf")
    assert word_counts("", "").error_rate == 0.0


def test_matches_reference_implementation_on_random_input():
    rng = random.Random(1)
    vocab = list("abcde")
    for _ in range(300):
        a = [rng.choice(vocab) for _ in range(rng.randint(0, 12))]
        b = [rng.choice(vocab) for _ in range(rng.randint(0, 12))]
        c = align_counts(a, b)
        assert c.errors == _reference_levenshtein(a, b)
        assert c.substitutions + c.deletions == len(a) - (len(a) - c.substitutions - c.deletions)
        # antall korrekte ord kan ikke bli negativt
        assert len(a) - c.substitutions - c.deletions >= 0
        assert len(b) == len(a) - c.deletions + c.insertions


def test_char_counts():
    c = char_counts("hei", "hai")
    assert c.substitutions == 1 and c.reference_length == 3


def test_edit_counts_add():
    total = EditCounts(1, 2, 3, 10) + EditCounts(1, 0, 0, 5)
    assert total.to_dict() == {"substitutions": 2, "deletions": 2, "insertions": 3, "reference_length": 15, "errors": 7}


@pytest.mark.parametrize(
    "words, expected",
    [
        (["takk", "takk", "takk", "takk"], True),
        (["takk", "for", "det", "takk", "for", "det", "takk", "for", "det", "takk", "for", "det"], True),
        (["takk", "takk", "takk"], False),
        # Lang frase gjentatt (NB-Whisper medium på NPSC, 2026-10-16)
        ("undersøkelsene syner at risikoanalyse for et flertall av disse ikke".split() * 4, True),
        ("vegdirektoratet har heller ikke god nok informasjon for å følge opp at".split() * 3, False),
        (["en", "to", "tre", "fire", "fem", "seks"], False),
        ([], False),
    ],
)
def test_repetition_loop(words, expected):
    assert repetition_loop(words) is expected


def test_item_flags():
    f = item_flags("", "teksting av nicolai winther", word_counts("", "teksting av nicolai winther"))
    assert f["hallucination_on_silence"] and f["hallucination"]
    f = item_flags("hei på deg", "", word_counts("hei på deg", ""))
    assert f["empty_output"] and not f["hallucination"]
    long_hyp = " ".join(["ord"] * 3 + ["annet"] * 12)
    f = item_flags("tre ord her", long_hyp, word_counts("tre ord her", long_hyp))
    assert f["overlong"] and f["hallucination"]
