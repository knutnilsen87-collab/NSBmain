import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("download_models", Path(__file__).parents[2] / "scripts" / "download_models.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_alignment_heads_outside_decoder_are_replaced(tmp_path):
    _write(tmp_path / "ct2" / "config.json", {"alignment_heads": [[7, 0], [10, 17]], "lang_ids": [1]})
    _write(tmp_path / "hf" / "config.json", {"decoder_layers": 2, "decoder_attention_heads": 4})
    assert dm.fix_alignment_heads(tmp_path / "ct2", tmp_path / "hf") is True
    cfg = json.loads((tmp_path / "ct2" / "config.json").read_text())
    assert cfg["alignment_heads"] == [[1, 0], [1, 1], [1, 2], [1, 3]] and cfg["lang_ids"] == [1]


def test_valid_alignment_heads_are_kept(tmp_path):
    _write(tmp_path / "ct2" / "config.json", {"alignment_heads": [[7, 0], [10, 17]]})
    _write(tmp_path / "hf" / "config.json", {"decoder_layers": 32, "decoder_attention_heads": 20})
    assert dm.fix_alignment_heads(tmp_path / "ct2", tmp_path / "hf") is False
