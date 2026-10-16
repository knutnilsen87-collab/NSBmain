import json
import wave
from pathlib import Path

import pytest

from nsb_eval import report, silence
from nsb_eval.manifest import load_manifest, resolve_audio_path
from nsb_eval.runner import evaluate, main


def _wav(path: Path, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


@pytest.fixture
def speech_set(tmp_path):
    root = tmp_path / "proj"
    rows = [
        {"id": "a", "audio": "dataset/a.wav", "text": "Stortingets møte er lovlig satt", "dialect": "øst"},
        {"id": "b", "audio": "dataset/b.wav", "text": "klokka 21.00 i kveld", "dialect": "vest"},
        {"id": "c", "audio": "dataset/c.wav", "text": "%eee %unint", "dialect": "vest"},
        {"id": "d", "audio": "dataset/missing.wav", "text": "denne fila finnes ikke", "dialect": "nord"},
    ]
    for r in rows[:3]:
        _wav(root / r["audio"], 2.0)
    manifest = tmp_path / "set.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    answers = {"a.wav": "stortingets møte er lovlig satt", "b.wav": "klokka tjueen null null i kveld i kveld", "c.wav": "eh"}
    answers_file = tmp_path / "answers.json"
    answers_file.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    return root, manifest, answers_file


def test_resolve_audio_path_variants(tmp_path):
    assert resolve_audio_path("dataset/x.wav", tmp_path, None) == str(tmp_path / "dataset" / "x.wav")
    assert resolve_audio_path("dataset\\x.wav", tmp_path, None) == str(tmp_path / "dataset" / "x.wav")
    mapped = resolve_audio_path("F:\\NorwegianSpeechBase\\dataset\\x.wav", None, {"F:\\NorwegianSpeechBase": "F:\\prosjekter_MAIN\\NorwegianSpeechBase"})
    assert mapped == "F:\\prosjekter_MAIN\\NorwegianSpeechBase\\dataset\\x.wav"
    assert resolve_audio_path("F:\\a\\b.wav", tmp_path, None) == "F:\\a\\b.wav"


def test_manifest_rejects_duplicates(tmp_path):
    m = tmp_path / "m.jsonl"
    m.write_text('{"id":"x","audio":"a.wav","text":"a"}\n{"id":"x","audio":"b.wav","text":"b"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="dobbel id"):
        load_manifest(m)


def test_evaluate_end_to_end_with_mock(speech_set, tmp_path):
    root, manifest, answers = speech_set
    out = tmp_path / "out"
    s = evaluate(
        manifest=str(manifest),
        out_dir=str(out),
        backend_kind="mock",
        backend_kwargs={"answers_file": str(answers), "label": "mock-test"},
        audio_root=str(root),
        group_by=["dialect"],
        log=lambda *_: None,
    )
    assert s["items_total"] == 4
    assert s["items_failed"] == 1 and s["complete"] is False
    assert s["items_nonlexical_excluded"] == 1
    sp = s["speech"]
    # a: 0 feil av 5 ord, b: 2 innsettinger av 6 ord -> 2/11
    assert sp["items"] == 2
    assert sp["word_counts"]["reference_length"] == 11
    assert sp["word_counts"]["insertions"] == 2
    assert sp["wer"] == pytest.approx(2 / 11, abs=1e-6)
    assert sp["audio_seconds"] == pytest.approx(4.0)
    assert set(s["by_dialect"]) == {"øst", "vest"}
    assert s["model"]["model"] == "mock-test"
    assert len(s["manifest_sha256"]) == 64
    lines = (out / "items.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4


def test_resume_skips_done_and_retries_failed(speech_set, tmp_path):
    root, manifest, answers = speech_set
    out = tmp_path / "out"
    kwargs = {
        "manifest": str(manifest),
        "out_dir": str(out),
        "backend_kind": "mock",
        "backend_kwargs": {"answers_file": str(answers)},
        "audio_root": str(root),
        "log": lambda *_: None,
    }
    evaluate(**kwargs)
    _wav(root / "dataset/missing.wav", 1.0)  # fila dukker opp
    s = evaluate(**kwargs)
    assert s["items_failed"] == 0 and s["complete"] is True
    assert s["items_total"] == 4


def test_silence_set_and_report(tmp_path):
    manifest = silence.build(tmp_path / "sil")
    silence.build(tmp_path / "sil2")
    a = sorted((tmp_path / "sil" / "audio").glob("*.wav"))
    b = sorted((tmp_path / "sil2" / "audio").glob("*.wav"))
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]  # deterministisk
    answers = tmp_path / "ans.json"
    answers.write_text(json.dumps({"white_noise_-35db_20s.wav": "Teksting av Nicolai Winther"}), encoding="utf-8")
    out = tmp_path / "results" / "silence_v1" / "mock"
    s = evaluate(manifest=str(manifest), out_dir=str(out), backend_kind="mock",
                 backend_kwargs={"answers_file": str(answers)}, audio_root=str(tmp_path / "sil"),
                 testset="silence_v1", log=lambda *_: None)
    assert s["silence"]["items"] == len(silence.CLIPS)
    assert s["silence"]["hallucination_on_silence_items"] == 1
    assert s["silence"]["inserted_words"] == 4
    assert s["speech"]["wer"] is None
    md_path = tmp_path / "results" / "BENCHMARK.md"
    assert report.main(["--results", str(tmp_path / "results"), "--out", str(md_path)]) == 0
    text = md_path.read_text(encoding="utf-8")
    assert "silence_v1" in text and "8.3 %" in text


def test_cli_exit_codes(speech_set, tmp_path):
    root, manifest, answers = speech_set
    code = main(["--manifest", str(manifest), "--out-dir", str(tmp_path / "cli"), "--backend", "mock",
                 "--answers-file", str(answers), "--audio-root", str(root)])
    assert code == 2  # én fil mangler
    with pytest.raises(SystemExit):
        main(["--manifest", str(manifest), "--out-dir", str(tmp_path / "x")])  # mangler --model


def test_resume_refuses_other_model(speech_set, tmp_path):
    root, manifest, answers = speech_set
    out = tmp_path / "same"
    base = {"manifest": str(manifest), "out_dir": str(out), "backend_kind": "mock", "audio_root": str(root), "log": lambda *_: None}
    evaluate(**base, backend_kwargs={"answers_file": str(answers), "label": "modell-a"})
    with pytest.raises(SystemExit, match="annen kjøring"):
        evaluate(**base, backend_kwargs={"answers_file": str(answers), "label": "modell-b"})
    s = evaluate(**base, backend_kwargs={"answers_file": str(answers), "label": "modell-b"}, resume=False)
    assert s["model"]["model"] == "modell-b"


def test_rescore_recomputes_from_raw_text(speech_set, tmp_path):
    from nsb_eval import rescore

    root, manifest, answers = speech_set
    out = tmp_path / "res" / "set" / "mock"
    evaluate(manifest=str(manifest), out_dir=str(out), backend_kind="mock",
             backend_kwargs={"answers_file": str(answers)}, audio_root=str(root), group_by=["dialect"], log=lambda *_: None)
    items = out / "items.jsonl"
    rows = [json.loads(line) for line in items.read_text(encoding="utf-8").splitlines()]
    for r in rows:  # simuler gammel normalisering: feil lagrede normaliserte felt
        if "reference_norm" in r:
            r["reference_norm"] = "noe helt annet"
            r["words"] = {"substitutions": 99, "deletions": 0, "insertions": 0, "reference_length": 3}
    items.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert rescore.main(["--results", str(tmp_path / "res")]) == 0
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["speech"]["wer"] == pytest.approx(2 / 11, abs=1e-6)
    assert "rescored_utc" in s and "by_dialect" in s
    assert "v4" in s["normalizer"]
    # Radene skrives på nytt, slik at de stemmer med summary.json
    fresh = [json.loads(line) for line in items.read_text(encoding="utf-8").splitlines()]
    assert len(fresh) == len(rows)
    assert all(r.get("reference_norm") != "noe helt annet" for r in fresh)
    assert sum(r["words"]["errors"] for r in fresh if "words" in r) == 2


def test_groups_without_metadata_are_named_ukjent(tmp_path):
    from nsb_eval.runner import score_item, summarize

    rows = [score_item("a", "hei der", "hei der", {}), score_item("b", "hei", "hei", {"dialect": None})]
    s = summarize(rows, group_by=["dialect"])
    assert list(s["by_dialect"]) == ["ukjent"]


def test_language_from_meta_passes_per_item_language(speech_set, tmp_path, monkeypatch):
    from nsb_eval import backends

    seen = []
    orig = backends.MockBackend.transcribe

    def spy(self, audio_path, language=None):
        seen.append(language)
        return orig(self, audio_path, language)

    monkeypatch.setattr(backends.MockBackend, "transcribe", spy)
    root, manifest, answers = speech_set
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    rows[0]["standard"], rows[1]["standard"] = "nn", "bm"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    s = evaluate(manifest=str(manifest), out_dir=str(tmp_path / "lang"), backend_kind="mock",
                 backend_kwargs={"answers_file": str(answers)}, audio_root=str(root),
                 language_from_meta="standard", log=lambda *_: None)
    assert seen[:2] == ["nn", "no"] and s["language_from_meta"] == "standard"
