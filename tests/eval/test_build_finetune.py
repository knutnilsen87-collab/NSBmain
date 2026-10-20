import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_finetune_dialect", Path(__file__).parents[2] / "scripts" / "build_finetune_dialect.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def _jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _nbs(split, i, speaker, rec, ortho="bm", text=None, dur=5.0):
    return {"source_file_id": rec, "segment_id": str(i), "segment_order": i, "duration": dur,
            "overlap_previous": False, "overlap_next": False, "speaker_id": speaker, "gender": "m", "dialect": "w",
            "orthography": ortho, "source_type": "podcast", "file_name": f"data/{split}/{ortho}/s{i}.wav",
            "transcription": text or f"dette er setning nummer {i} i {split}"}


def _npsc(meeting, sid, speaker, lang="nb-NO", text=None):
    return {"meeting_date": meeting, "speaker_id": speaker, "speaker_dialect": "Western Norway", "sentence_id": sid,
            "sentence_language_code": lang, "sentence_text": text or f"stortinget behandler sak nummer {sid} nå",
            "audio": f"{meeting}/audio/{sid}.wav"}


def make_root(tmp_path: Path) -> Path:
    root = tmp_path
    nbs = []
    # Fem talergrupper (opptak som deler taler): A+B (største), C, D, E (minst).
    # Gruppe A: opptak a1 og a2 deler taler P1.
    for i in range(12):
        nbs.append(_nbs(["train", "dev", "test"][i % 3], i, "P1" if i < 8 else "P2", "a1" if i < 6 else "a2",
                        "nn" if i % 4 == 0 else "bm", dur=10.0))
    nbs += [_nbs("train", 20 + i, "P3", "b1", dur=8.0) for i in range(6)]
    nbs += [_nbs("train", 40 + i, "P4", "c1", "nn" if i % 2 else "bm", dur=6.0) for i in range(5)]
    nbs += [_nbs("dev", 60 + i, "P5", "d1", "nn" if i % 2 else "bm", dur=5.0) for i in range(6)]
    nbs += [_nbs("test", 80 + i, "P6", "e1", dur=2.0) for i in range(3)]
    nbs += [_nbs("train", 99, "P3", "b1", text="en låst test setning med mange ord")]  # tekst fra låst test
    _jsonl(root / "dataset/nb_samtale/metadata.jsonl", nbs)
    base = root / "dataset/norwegian"
    for m in ("20170110", "20170207", "20170209"):
        (base / "NPSC_1" / m).mkdir(parents=True)
    (base / "NPSC_2").mkdir(parents=True)
    _jsonl(base / "NPSC_1/NPSC_2_0_train.jsonl", [
        _npsc("20170110", 1, 10), _npsc("20170110", 2, 10, "nn-NO"), _npsc("20170110", 3, 77),  # 77 er i låst test
        _npsc("20170110", 4, 10, "en-US"), _npsc("20170315", 5, 10),  # ikke lokalt
        _npsc("20170207", 6, 10),  # låst møte
    ])
    _jsonl(base / "NPSC_1/NPSC_2_0_test.jsonl", [_npsc("20170207", 50, 77)])
    _jsonl(base / "NPSC_1/NPSC_2_0_eval.jsonl", [_npsc("20170209", 60, 78)])
    _jsonl(root / "eval/testsets/npsc_test_20170207.jsonl", [{"id": "a", "audio": "x", "text": "noe helt annet her i dag"}])
    _jsonl(root / "eval/testsets/npsc_eval_20170209.jsonl",
           [{"id": f"e{i}", "audio": f"e{i}.wav", "text": f"eval setning {i} med ord"} for i in range(3)])
    _jsonl(root / "eval/testsets/nb_samtale_test.jsonl", [{"id": "t", "audio": "y", "text": "En låst test-setning med mange ord."}])
    return root


def test_nb_samtale_is_split_without_shared_speakers(tmp_path):
    root = make_root(tmp_path)
    parts = bf.split_nb_samtale(bf.nb_samtale_all(root))
    recs = {k: {r["recording"] for r in v} for k, v in parts.items()}
    assert recs["train"] == {"a1", "a2", "b1"} and recs["test"] == {"c1", "e1"} and recs["dev"] == {"d1"}
    spk = {k: {r["speaker_id"] for r in v} for k, v in parts.items()}
    assert not (spk["train"] & spk["test"]) and not (spk["train"] & spk["dev"])


def test_build_excludes_locked_speakers_meetings_and_texts(tmp_path):
    root = make_root(tmp_path)
    stats = bf.build(root, root / "out", npsc_max=10)
    train = [json.loads(line) for line in (root / "out/train.jsonl").read_text(encoding="utf-8").splitlines()]
    speakers = {r["speaker_id"] for r in train}
    assert "npsc-77" not in speakers and not speakers & {"nbs-P4", "nbs-P5", "nbs-P6"}
    assert all("20170207" not in r["audio"] and "20170315" not in r["audio"] for r in train)
    assert not any("låst test" in r["text"] for r in train)
    assert not any(r.get("official_split") == "test" for r in train)  # offisiell testsplitt trenes aldri på
    assert {r["id"] for r in train if r["source"] == "npsc"} == {"npsc-1", "npsc-2"}
    assert {r["language"] for r in train} == {"no", "nn"}
    assert next(r for r in train if r["id"] == "npsc-2")["language"] == "nn"
    assert stats["dropped"]["locked_text"] == 1 and stats["dropped"]["nb_samtale_official_test"] == 4
    assert stats["builder_version"] == bf.BUILDER_VERSION
    # Samme dialektnavn i begge kilder; nøkler som bare skiller seg på store/små bokstaver
    # knekker ConvertFrom-Json i PowerShell 5.1.
    assert next(r for r in train if r["id"] == "npsc-1")["dialect"] == "vest"
    keys = list(stats["train"]["by_dialect"])
    assert len({k.lower() for k in keys}) == len(keys)


def test_validation_and_locked_test_manifests(tmp_path):
    root = make_root(tmp_path)
    bf.build(root, root / "out")
    val = [json.loads(line) for line in (root / "out/val.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["source"] for r in val} == {"nb_samtale", "npsc_eval"}
    assert {r["language"] for r in val} == {"no", "nn"}
    dev = (root / "eval/testsets/nb_samtale_spk_dev.jsonl").read_text(encoding="utf-8").splitlines()
    test = [json.loads(line) for line in (root / "eval/testsets/nb_samtale_spk_test.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(dev) == 6 and "language" not in json.loads(dev[0])
    assert {r["recording"] for r in test} == {"c1", "e1"} and all("standard" in r and "dialect" in r for r in test)


def test_build_is_deterministic(tmp_path):
    root = make_root(tmp_path)
    a = bf.build(root, root / "a")["sha256"]
    b = bf.build(root, root / "b")["sha256"]
    assert a == b
