"""Laster ned modellene i målestokken i CTranslate2-format (for faster-whisper).

    python scripts/download_models.py --out models/benchmark

NB-Whisper-repoene på Hugging Face har en ferdig konvertert ``ct2``-mappe.
Mangler den, konverteres modellen med ``ct2-transformers-converter``
(krever ``transformers`` og ``torch``). Skriver ``models.json`` med lokal
sti per modell, som ``run_benchmark.ps1`` leser.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

MODELS = {
    "nb-whisper-large": {"repo": "NbAiLab/nb-whisper-large", "subdir": "ct2"},
    "nb-whisper-large-distil-turbo-beta": {"repo": "NbAiLab/nb-whisper-large-distil-turbo-beta", "subdir": "ct2"},
    "nb-whisper-medium": {"repo": "NbAiLab/nb-whisper-medium", "subdir": "ct2"},
    "nb-whisper-small": {"repo": "NbAiLab/nb-whisper-small", "subdir": "ct2"},
    "whisper-large-v3": {"repo": "Systran/faster-whisper-large-v3", "subdir": ""},
}


def _has_ct2(path: Path) -> bool:
    return (path / "model.bin").exists() and (path / "config.json").exists()


def fetch(name: str, spec: dict, out: Path) -> dict:
    from huggingface_hub import snapshot_download

    target = out / name
    sub = spec["subdir"]
    patterns = [f"{sub}/*"] if sub else None
    local = Path(snapshot_download(spec["repo"], local_dir=str(target), allow_patterns=patterns))
    model_dir = local / sub if sub else local
    if _has_ct2(model_dir):
        # Tokenizer-filene ligger ofte i roten; faster-whisper trenger tokenizer.json ved siden av model.bin.
        if not (model_dir / "tokenizer.json").exists():
            snapshot_download(spec["repo"], local_dir=str(target), allow_patterns=["tokenizer.json", "preprocessor_config.json"])
            for f in ("tokenizer.json", "preprocessor_config.json"):
                if (target / f).exists() and not (model_dir / f).exists():
                    shutil.copy(target / f, model_dir / f)
        return {"name": name, "repo": spec["repo"], "path": str(model_dir.resolve()), "converted": False}

    # Ingen ferdig CT2: last ned Transformers-vektene og konverter.
    hf_dir = Path(snapshot_download(spec["repo"], local_dir=str(target / "hf"),
                                    allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"]))
    ct2_dir = target / "ct2_converted"
    if not _has_ct2(ct2_dir):
        subprocess.run(
            ["ct2-transformers-converter", "--model", str(hf_dir), "--output_dir", str(ct2_dir),
             "--copy_files", "tokenizer.json", "preprocessor_config.json", "--quantization", "float16", "--force"],
            check=True,
        )
    return {"name": name, "repo": spec["repo"], "path": str(ct2_dir.resolve()), "converted": True}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="models/benchmark")
    ap.add_argument("--only", action="append", help="Bare disse modellene (kan gjentas)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    registry_path = out / "models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    failed = []
    for name, spec in MODELS.items():
        if args.only and name not in args.only:
            continue
        try:
            registry[name] = fetch(name, spec, out)
            print(f"[ok] {name} -> {registry[name]['path']}")
        except Exception as exc:  # noqa: BLE001 - én modell skal ikke stoppe resten
            failed.append(name)
            registry[name] = {"name": name, "repo": spec["repo"], "error": f"{type(exc).__name__}: {exc}"}
            print(f"[feil] {name}: {exc}", file=sys.stderr)
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
