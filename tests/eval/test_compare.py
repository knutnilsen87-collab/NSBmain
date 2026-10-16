import json

import pytest

from nsb_eval.compare import load_errors, main, paired_bootstrap


def test_identical_models_differ_by_zero():
    a = {str(i): (i % 3, 10) for i in range(50)}
    r = paired_bootstrap(a, dict(a), rounds=200)
    assert r["diff_pp"] == 0 and r["ci95_pp"] == [0, 0] and not r["significant"]


def test_clearly_worse_model_is_significant():
    good = {str(i): (1, 10) for i in range(200)}
    bad = {str(i): (4, 10) for i in range(200)}
    r = paired_bootstrap(bad, good, rounds=300)
    assert r["diff_pp"] == pytest.approx(30.0)
    assert r["significant"] and r["ci95_pp"][0] > 0


def test_only_shared_items_are_compared():
    a = {"x": (1, 10), "y": (5, 10)}
    b = {"x": (1, 10)}
    assert paired_bootstrap(a, b, rounds=50)["items"] == 1


def test_no_shared_items_raises():
    with pytest.raises(ValueError):
        paired_bootstrap({"a": (1, 1)}, {"b": (1, 1)})


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_cli_reads_items_and_skips_failed_and_empty(tmp_path, capsys):
    ok = [{"id": str(i), "words": {"errors": 1, "reference_length": 10}} for i in range(20)]
    _write(tmp_path / "set" / "base" / "items.jsonl", ok + [{"id": "f", "error": "boom"}])
    worse = [{"id": str(i), "words": {"errors": 3, "reference_length": 10}} for i in range(20)]
    _write(tmp_path / "set" / "other" / "items.jsonl", worse + [{"id": "e", "words": {"errors": 0, "reference_length": 0}}])
    assert len(load_errors(tmp_path / "set" / "base" / "items.jsonl")) == 20
    assert main(["--results", str(tmp_path), "--testset", "set", "--baseline", "base", "--rounds", "100"]) == 0
    out = capsys.readouterr().out
    assert "other minus base: +20.0 pp" in out and "signifikant" in out
