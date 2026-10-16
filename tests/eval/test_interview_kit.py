import json
import sys
from pathlib import Path

from nsb_eval.critical import critical_counts
from nsb_eval.manifest import load_manifest
from nsb_eval.normalize import normalize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "py"))
import nsb_record_interview as rec  # noqa: E402


def test_scripts_are_complete_and_fictional_ids_unique():
    ivs = rec.load_scripts()
    assert [iv["id"] for iv in ivs] == ["av-01", "av-02", "av-03"]
    for iv in ivs:
        assert len(iv["roles"]) == 2
        assert all(t["speaker"] in iv["roles"] and t["say"].strip() for t in iv["turns"])


def test_each_script_has_critical_details_to_measure():
    for iv in rec.load_scripts():
        ref = rec.reference_text(iv)
        c = critical_counts(ref, normalize(ref), "")
        assert c["negation"]["reference"] >= 3, iv["id"]
        assert c["number"]["reference"] >= 3, iv["id"]
        assert c["name"]["reference"] >= 2, iv["id"]


def test_unverified_rows_are_skipped(tmp_path):
    iv = rec.load_scripts()[0]
    rows = [rec.manifest_row(iv, "a.wav", "s1", ["a", "b"]), {**rec.manifest_row(iv, "b.wav", "s2", ["a", "b"]), "verified": True}]
    m = tmp_path / "manifest.jsonl"
    m.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    items = load_manifest(m)
    assert [i.id for i in items] == ["s2-av-01"]
