"""Sjekker at lydfilene i testsettene finnes før en lang kjøring starter.

    python -m nsb_eval.preflight --root . --testset npsc_test_20170207 --testset nb_samtale_test

Avslutter med kode 1 og lister de første manglende filene hvis noe mangler.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .manifest import load_manifest
from .recorded import RECORDED_SETS, combined_manifest


def manifest_for(root: Path, name: str) -> tuple[Path, Path]:
    if name in RECORDED_SETS:
        return combined_manifest(root, name), root
    if name == "silence_v1":
        base = root / "eval" / "testsets" / "silence_v1"
        return base / "manifest.jsonl", base
    return root / "eval" / "testsets" / f"{name}.jsonl", root


def check(root: Path, testsets: list[str], limit: int | None = None) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for name in testsets:
        manifest, audio_root = manifest_for(root, name)
        if not manifest.exists():
            missing[name] = [f"manifest mangler: {manifest}"]
            continue
        items = load_manifest(manifest, audio_root=audio_root)
        if limit:
            items = items[:limit]
        lost = [it.audio for it in items if not Path(it.audio).exists()]
        if lost:
            missing[name] = lost
    return missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--testset", action="append", required=True)
    ap.add_argument("--limit", type=int, default=None, help="Sjekk bare de første N setningene per sett")
    args = ap.parse_args(argv)
    missing = check(Path(args.root), args.testset, args.limit)
    for name, files in missing.items():
        print(f"[mangler] {name}: {len(files)} filer, f.eks. {files[:3]}")
    if not missing:
        print(f"[ok] alle lydfiler finnes for {', '.join(args.testset)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
