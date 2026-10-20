import json
from pathlib import Path

import pytest

from nsb_train_utils import clean_training_text, group_bucket, shuffle_buffer, strip_decoder_start, validate_out_dir
from split_by_group import split


@pytest.mark.parametrize(
    "raw, expected, reason",
    [
        ("(...Vær stille under dette opptaket...)", None, "silence_prompt"),
        ("(latter)", None, "silence_prompt"),
        ("", None, "empty"),
        (None, None, "empty"),
        ("det var <INAUDIBLE> sa han", None, "uncertain_segment"),
        ("%unint og så videre", None, "uncertain_segment"),
        ("Dersom sykdommen ikke kommer under kontroll,\\Komma kan den bli et problem.\\Punktum",
         "Dersom sykdommen ikke kommer under kontroll, kan den bli et problem.", "ok"),
        ("Kommer dere?\\Spørsmålstegn", "Kommer dere?", "ok"),
        ("at dokker\\dere er her", "at dere er her", "ok"),
        ("med N_R_K-appen\\NRK-appen er s£ bra", "med NRK-appen er bra", "ok"),
        ("%eee så velkommen", "så velkommen", "ok"),
        ("landets +befolkning", "landets befolkning", "ok"),
        ("%eee", None, "no_words_after_cleaning"),
        ("Anette Østensen", "Anette Østensen", "ok"),
    ],
)
def test_clean_training_text(raw, expected, reason):
    assert clean_training_text(raw) == (expected, reason)


def test_dictation_word_mode():
    text, _ = clean_training_text("under kontroll,\\Komma kan den bli et problem.\\Punktum", dictation="word")
    assert text == "under kontroll komma kan den bli et problem punktum"


def test_shuffle_buffer_is_deterministic_and_complete():
    data = list(range(1000))
    a = list(shuffle_buffer(data, 100, seed=1))
    b = list(shuffle_buffer(data, 100, seed=1))
    c = list(shuffle_buffer(data, 100, seed=2))
    assert a == b and a != c
    assert sorted(a) == data and a != data
    assert list(shuffle_buffer(data, 1, seed=1)) == data


def test_shuffle_buffer_spreads_early_items():
    # Med buffer på 500 skal de første 100 utdataene ikke bare være de første 100 inndataene.
    out = list(shuffle_buffer(range(5000), 500, seed=3))[:100]
    assert max(out) > 200


def test_strip_decoder_start():
    assert strip_decoder_start([50258, 50288, 50359, 1, 2, 50257], 50258) == [50288, 50359, 1, 2, 50257]
    assert strip_decoder_start([1, 2], 50258) == [1, 2]
    assert strip_decoder_start([], 50258) == []


@pytest.mark.parametrize("bad", ["True", "False", "$true", " ", "None"])
def test_validate_out_dir_rejects_powershell_bools(bad):
    with pytest.raises(ValueError):
        validate_out_dir(bad)


def test_validate_out_dir_accepts_paths():
    assert validate_out_dir("build/models/run1") == "build/models/run1"


def test_group_bucket_stable():
    assert group_bucket("no18x015") == group_bucket("no18x015")
    assert 0 <= group_bucket("x", 10) < 10


def _rows():
    rows = []
    for spk in range(200):
        for k in range(5):
            text = "felles manus setning" if k == 0 else f"taler {spk} setning {k}"
            rows.append({"audio": f"F:/data/lydfiler/no/no{spk:02d}x{spk:03d}-sess/u{k}.wav", "text": text})
    return rows


def test_split_by_speaker_has_no_speaker_overlap_and_no_text_leakage():
    parts, summary = split(_rows(), val_pct=5.0, test_pct=5.0, group_regex=r"(no\d+x\d+)")
    def speakers(p):
        return {r["audio"].split("/")[-2] for r in parts[p]}
    assert not speakers("train") & speakers("val")
    assert not speakers("train") & speakers("test")
    assert summary["counts"]["val"] > 0 and summary["counts"]["test"] > 0
    eval_texts = {r["text"] for p in ("val", "test") for r in parts[p]}
    assert not any(r["text"] in eval_texts for r in parts["train"])
    assert summary["dropped_train_text_overlap"] > 0


def test_split_excludes_fixed_testsets():
    rows = _rows()
    target = rows[7]["audio"]
    tail = "/".join(target.lower().split("/")[-3:])
    parts, summary = split(rows, 5.0, 5.0, group_regex=r"(no\d+x\d+)", exclude_tails={tail}, text_leakage="ignore")
    assert summary["excluded_fixed_testset"] == 1
    assert all(r["audio"] != target for p in parts.values() for r in p)


def test_fixed_testsets_are_never_in_training_manifests_by_tail():
    root = Path(__file__).resolve().parents[2]
    tails = set()
    for m in (root / "eval" / "testsets").glob("*.jsonl"):
        for line in m.read_text(encoding="utf-8").splitlines():
            tails.add("/".join(json.loads(line)["audio"].lower().split("/")[-3:]))
    # NPSC test + eval, og NB Samtale: offisiell test (1 195) og de talerdelte
    # settene (2 444 + 1 091), som overlapper med den offisielle testen.
    assert len(tails) == 501 + 582 + 4385


def test_split_excludes_by_text_and_path_substring():
    rows = _rows() + [
        {"audio": "F:/annet/sted/kopi_av_testlyd.wav", "text": "Stortingets møte er lovlig satt i dag"},
        {"audio": "F:/npsc/20170207/audio/x.wav", "text": "en helt annen setning her nå"},
    ]
    parts, summary = split(
        rows, 5.0, 5.0, group_regex=r"(no\d+x\d+)", text_leakage="ignore",
        exclude_texts={"stortingets møte er lovlig satt i dag"}, exclude_path_contains=["20170207"],
    )
    assert summary["excluded_fixed_testset_text"] == 1
    assert summary["excluded_path_match"] == 1
    kept = {r["audio"] for p in parts.values() for r in p}
    assert "F:/annet/sted/kopi_av_testlyd.wav" not in kept and "F:/npsc/20170207/audio/x.wav" not in kept
