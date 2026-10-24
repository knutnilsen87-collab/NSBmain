import pytest

from nsb_eval.decoding import collapse_loops, collapse_text, profile
from nsb_eval.metrics import repetition_loop


def test_collapse_keeps_natural_repeats_and_cuts_loops():
    assert collapse_text("er du er du gjer") == "er du er du gjer"
    assert collapse_text("takk takk takk") == "takk takk takk"
    assert collapse_text("det det det det handlar om") == "det det handlar om"
    assert collapse_text("er du er du er du er du masse") == "er du er du masse"
    long = "og så " + " ".join(["vi gikk dit"] * 9) + " til slutt"
    out = collapse_text(long)
    assert out == "og så vi gikk dit vi gikk dit til slutt"
    assert not repetition_loop(out.split())


def test_collapse_on_word_objects_ignores_punctuation():
    words = [("Ja,", 0), ("ja", 1), ("ja", 2), ("ja.", 3), ("ok", 4)]
    assert [t for _, t in collapse_loops(words, key=lambda w: w[0])] == [0, 1, 4]


def test_profiles():
    assert profile("standard") == {"temperature": 0.0}
    assert profile("loopvakt_ngram")["no_repeat_ngram_size"] == 4
    with pytest.raises(ValueError):
        profile("finnes-ikke")
