import pytest

from nsb_eval.critical import align_ops, critical_counts, name_words
from nsb_eval.metrics import align_counts
from nsb_eval.normalize import normalize
from nsb_eval.resources import PeakMemory


def crit(ref_raw, hyp_raw):
    return critical_counts(ref_raw, normalize(ref_raw), normalize(hyp_raw))


@pytest.mark.parametrize(
    "ref, hyp",
    [
        ("a b c d", "a x c"),
        ("en to tre", "en to tre fire fem"),
        ("", "noe"),
        ("noe her", ""),
        ("han kom ikke i går", "han kom i går i går"),
    ],
)
def test_align_ops_agree_with_align_counts(ref, hyp):
    r, h = ref.split(), hyp.split()
    ops = align_ops(r, h)
    c = align_counts(r, h)
    assert sum(op == "sub" for op, *_ in ops) + sum(op == "del" for op, *_ in ops) + sum(op == "ins" for op, *_ in ops) == c.errors
    assert [x for op, x, _ in ops if op != "ins"] == r
    assert [y for op, _, y in ops if op != "del"] == h


def test_dropped_negation_is_counted():
    c = crit("Vitnet så ikke bilen.", "Vitnet så bilen.")
    assert c["negation"] == {"reference": 1, "missed": 1, "added": 0}


def test_added_negation_is_counted():
    c = crit("Han hadde betalt.", "Han hadde ikke betalt.")
    assert c["negation"]["added"] == 1 and c["negation"]["reference"] == 0


def test_negation_swapped_for_other_negation_is_not_missed():
    c = crit("det var ingen der", "det var ikke der")
    assert c["negation"]["missed"] == 0


def test_numbers_compare_as_digits():
    assert crit("Beløpet var hundre og enogsytti kroner.", "Beløpet var 171 kroner.")["number"] == {"reference": 1, "missed": 0}
    assert crit("Beløpet var 171 kroner.", "Beløpet var 117 kroner.")["number"] == {"reference": 1, "missed": 1}


def test_names_exclude_sentence_starts():
    assert name_words("Stortingets møte er satt. Representanten Gunvor Eldegard har ordet.") == {"gunvor", "eldegard"}


def test_missed_name_is_counted():
    c = crit("Så kom Hege Haukeland Liadal inn.", "Så kom Hege Haukland Liadal inn.")
    assert c["name"] == {"reference": 3, "missed": 1}


def test_verbatim_profile_keeps_fillers_and_truncated_words():
    raw = "<ee> han ble£ blitt %eee sett"
    assert normalize(raw) == "han blitt sett"
    assert normalize(raw, "ordrett") == "eh han ble blitt eh sett"
    assert normalize("han eh ehm kom", "ordrett") == "han eh eh kom"
    assert normalize("%heh ja %ttt", "ordrett") == "ja"


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        normalize("x", "fri")


def test_peak_memory_reports_ram_without_gpu():
    with PeakMemory(interval=0.05, gpu=False) as pm:
        _ = [0] * 1_000_000
    r = pm.result()
    assert r["peak_rss_mb"] and r["peak_rss_mb"] > 0
    assert r["peak_gpu_mb"] is None


def test_ikke_sant_is_not_a_negation():
    c = crit("det er fint ikke sant og han kom ikke", "det er fint og han kom ikke")
    assert c["negation"] == {"reference": 1, "missed": 0, "added": 0}


def test_article_en_is_not_counted_as_number():
    c = crit("dette er en retningslinje på tre sider", "dette er retningslinjer på 3 sider")
    assert c["number"] == {"reference": 1, "missed": 0}
