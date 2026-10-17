import json

import pytest

from nsb_eval import preflight
from nsb_eval.manifest import load_manifest
from nsb_eval.recorded import collect, combined_manifest


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_collect_merges_speakers_and_skips_unverified(tmp_path):
    base = tmp_path / "eval" / "recording"
    _write(base / "legal_dictation_v1" / "knut" / "manifest.jsonl", [
        {"id": "knut-jd-001", "audio": "eval/recording/legal_dictation_v1/knut/jd-001.wav", "text": "a", "category": "lov"},
        {"id": "knut-jd-002", "audio": "eval/recording/legal_dictation_v1/knut/jd-002.wav", "text": "b", "category": "tall"},
    ])
    _write(base / "legal_dictation_v1" / "kari" / "manifest.jsonl", [
        {"id": "kari-jd-001", "audio": "eval/recording/legal_dictation_v1/kari/jd-001.wav", "text": "a", "verified": False},
    ])
    r = collect(tmp_path, "legal_dictation_v1")
    assert r["rows"] == 2 and r["groups"] == {"knut": 2} and r["unverified_skipped"] == 1
    items = load_manifest(combined_manifest(tmp_path, "legal_dictation_v1"), audio_root=tmp_path)
    assert [i.id for i in items] == ["knut-jd-001", "knut-jd-002"]
    assert items[0].meta["speaker_id"] == "knut" and items[0].audio.startswith(str(tmp_path))


def test_preflight_finds_missing_recordings(tmp_path):
    _write(tmp_path / "eval" / "recording" / "simulated_interview_v1" / "s1" / "manifest.jsonl", [
        {"id": "s1-av-01", "audio": "eval/recording/simulated_interview_v1/s1/av-01.wav", "text": "x", "verified": True},
    ])
    collect(tmp_path, "simulated_interview_v1")
    missing = preflight.check(tmp_path, ["simulated_interview_v1"])
    assert "simulated_interview_v1" in missing
    wav = tmp_path / "eval" / "recording" / "simulated_interview_v1" / "s1" / "av-01.wav"
    wav.write_bytes(b"RIFF")
    assert preflight.check(tmp_path, ["simulated_interview_v1"]) == {}


def test_unknown_set_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        collect(tmp_path, "lia")
