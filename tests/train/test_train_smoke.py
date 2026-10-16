"""Røyktest av treningsskriptet med en bitte liten, tilfeldig Whisper-modell.

Krever torch, transformers og en mappe med Whisper-tokenizerfiler i
``NSB_TOKENIZER_DIR`` (for eksempel et lokalt checkpoint). Hoppes over i CI.
"""

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

TOKENIZER_DIR = os.environ.get("NSB_TOKENIZER_DIR")
pytestmark = pytest.mark.skipif(not TOKENIZER_DIR, reason="NSB_TOKENIZER_DIR ikke satt")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "python" / "train_whisper_iterable.py"
TOKENIZER_FILES = [
    "added_tokens.json", "merges.txt", "normalizer.json", "preprocessor_config.json",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.json",
]


def _tone(path: Path, freq: float, seconds: float = 1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * t / 16000))) for t in range(int(16000 * seconds))))


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory):
    d = tmp_path_factory.mktemp("tiny-whisper")
    for f in TOKENIZER_FILES:
        shutil.copy(Path(TOKENIZER_DIR) / f, d / f)
    base = json.loads((Path(TOKENIZER_DIR) / "config.json").read_text(encoding="utf-8"))
    cfg = transformers.WhisperConfig(
        vocab_size=base["vocab_size"], num_mel_bins=80, d_model=32, encoder_layers=1, decoder_layers=1,
        encoder_attention_heads=2, decoder_attention_heads=2, encoder_ffn_dim=64, decoder_ffn_dim=64,
        decoder_start_token_id=base["decoder_start_token_id"], eos_token_id=base["eos_token_id"],
        pad_token_id=base["pad_token_id"], bos_token_id=base["bos_token_id"],
        max_target_positions=448, max_source_positions=1500,
    )
    torch.manual_seed(0)
    model = transformers.WhisperForConditionalGeneration(cfg)
    model.save_pretrained(d)
    gen = json.loads((Path(TOKENIZER_DIR) / "generation_config.json").read_text(encoding="utf-8"))
    (d / "generation_config.json").write_text(json.dumps(gen), encoding="utf-8")
    return d


@pytest.fixture(scope="module")
def tiny_data(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    texts = ["hei på deg", "dette er en test", "kontroll,\\Komma sa han", "(...Vær stille under dette opptaket...)", "god morgen", "takk for nå"]
    rows = []
    for i, t in enumerate(texts):
        wav = d / f"u{i}.wav"
        _tone(wav, 200 + 50 * i)
        rows.append({"audio": str(wav), "text": t})
    rows.append({"audio": str(d / "finnes_ikke.wav"), "text": "korrupt"})
    (d / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (d / "val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[:2]), encoding="utf-8")
    return d


def test_labels_have_language_task_and_eos(tiny_model):
    sys.path.insert(0, str(SCRIPT.parent))
    import train_whisper_iterable as tw

    proc = transformers.WhisperProcessor.from_pretrained(tiny_model)
    proc.tokenizer.set_prefix_tokens(language="no", task="transcribe")
    ids = proc.tokenizer("hei").input_ids
    toks = proc.tokenizer.convert_ids_to_tokens(ids)
    assert toks[:3] == ["<|startoftranscript|>", "<|no|>", "<|transcribe|>"]
    assert toks[-1] == "<|endoftext|>"
    cfg = transformers.WhisperConfig.from_pretrained(tiny_model)
    coll = tw.Collator(proc, cfg.decoder_start_token_id)
    feats = torch.zeros(80, 3000)
    batch = coll([
        {"input_features": feats, "labels": torch.tensor(ids)},
        {"input_features": feats, "labels": torch.tensor(proc.tokenizer("hei på deg igjen").input_ids)},
    ])
    first = batch["labels"][0].tolist()
    assert first[0] != cfg.decoder_start_token_id  # start-token fjernet
    assert proc.tokenizer.eos_token_id in first  # sluttoken beholdt (ikke maskert bort)
    assert first[-1] == -100  # utfylling er maskert


def test_training_runs_saves_best_and_rotates(tiny_model, tiny_data, tmp_path):
    out = tmp_path / "run"
    cmd = [
        sys.executable, str(SCRIPT), "--train_jsonl", str(tiny_data / "train.jsonl"),
        "--val_jsonl", str(tiny_data / "val.jsonl"), "--out_dir", str(out), "--model_name", str(tiny_model),
        "--max_steps", "12", "--eval_steps", "4", "--save_steps", "4", "--logging_steps", "2",
        "--batch_size", "2", "--warmup_steps", "1", "--shuffle_size", "3", "--keep_last", "2",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
    assert res.returncode == 0, res.stderr[-3000:]
    metrics = [json.loads(line) for line in (out / "metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    evals = [m for m in metrics if "wer" in m]
    assert len(evals) == 3 and all(m["items"] == 2 for m in evals)
    data = evals[-1]["data"]
    assert data.get("skip_silence_prompt", 0) >= 1 and data.get("skip_bad_audio", 0) >= 1
    assert (out / "best" / "config.json").exists() and (out / "best_metrics.json").exists()
    steps = sorted(p.name for p in (out / "checkpoints").iterdir())
    assert steps == ["step-12", "step-8"]
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "DONE"


def test_rejects_true_as_out_dir(tiny_model, tiny_data):
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--train_jsonl", str(tiny_data / "train.jsonl"), "--val_jsonl",
         str(tiny_data / "val.jsonl"), "--out_dir", "True", "--model_name", str(tiny_model)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert res.returncode != 0 and "Ugyldig --out_dir" in res.stderr
