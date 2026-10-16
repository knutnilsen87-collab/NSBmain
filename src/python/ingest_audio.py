# -*- coding: utf-8 -*-
"""
NorwegianSpeechBase - ingest_audio.py (stable minimal)
- Scans --data_root recursively for .wav
- Writes build/ingest/manifest.jsonl
- Writes logs: audit.jsonl, errors.jsonl, timings.jsonl
- Accepts --root (ignored) for backward compatibility
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Tuple

# -----------------------------
# Utilities
# -----------------------------

def _now_iso() -> str:
    # Local time ISO-like without timezone dependency
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def _write_jsonl_line(fp, obj: dict) -> None:
    fp.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _safe_relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)

def _get_wav_duration_sec(wav_path: Path) -> Optional[float]:
    # Safe wav header read
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate and rate > 0:
                return float(frames) / float(rate)
    except Exception:
        return None
    return None

def _get_wav_meta(wav_path: Path) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """
    Returns: (duration_sec, sample_rate, channels)
    Uses stdlib wave; returns None values if unreadable.
    """
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            sr = wf.getframerate()
            ch = wf.getnchannels()
            dur = None
            if sr and sr > 0 and frames is not None:
                dur = float(frames) / float(sr)
            return dur, int(sr) if sr else None, int(ch) if ch else None
    except Exception:
        return None, None, None
def _walk_wavs(data_root: Path) -> Iterator[Path]:
    # Deterministic order: sort directories + filenames
    # Use os.walk with sorting for stability
    for dirpath, dirnames, filenames in os.walk(str(data_root)):
        dirnames.sort()
        filenames.sort()
        for fn in filenames:
            if fn.lower().endswith(".wav"):
                yield Path(dirpath) / fn

def _infer_speaker_id(wav_path: Path, data_root: Path) -> str:
    # Simple heuristic: first directory under root, else "unknown"
    rel = wav_path
    try:
        rel = wav_path.relative_to(data_root)
    except Exception:
        return "unknown"
    parts = rel.parts
    if len(parts) >= 2:
        return parts[0]
    return "unknown"

@dataclass
class IngestConfig:
    repo_root: Path
    data_root: Path
    build_dir: Path
    logs_dir: Path
    run_id: str
    no_duration: bool = False
    fail_on_empty: bool = True

def _make_run_id() -> str:
    # Deterministic enough per invocation without randomness
    # e.g. 20251225_153012
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())

# -----------------------------
# Main ingest
# -----------------------------

def ingest(cfg: IngestConfig) -> int:
    _ensure_dir(cfg.build_dir)
    _ensure_dir(cfg.logs_dir)

    ingest_dir = cfg.build_dir / "ingest"
    _ensure_dir(ingest_dir)

    manifest_path = ingest_dir / "manifest.jsonl"
    audit_path = cfg.logs_dir / "audit.jsonl"
    errors_path = cfg.logs_dir / "errors.jsonl"
    timings_path = cfg.logs_dir / "timings.jsonl"
    context_path = cfg.logs_dir / "context.json"

    t0 = time.perf_counter()

    # Open logs
    with open(audit_path, "a", encoding="utf-8") as audit_fp, \
         open(errors_path, "a", encoding="utf-8") as err_fp, \
         open(timings_path, "a", encoding="utf-8") as time_fp:

        # Context snapshot
        context = {
            "ts": _now_iso(),
            "runId": cfg.run_id,
            "repo_root": str(cfg.repo_root),
            "data_root": str(cfg.data_root),
            "build_dir": str(cfg.build_dir),
            "logs_dir": str(cfg.logs_dir),
            "script": "ingest_audio.py",
            "version": "stable-minimal-1",
            "python": sys.version,
            "platform": sys.platform,
        }
        with open(context_path, "w", encoding="utf-8") as cfp:
            json.dump(context, cfp, ensure_ascii=False, indent=2)

        _write_jsonl_line(audit_fp, {
            "ts": _now_iso(),
            "runId": cfg.run_id,
            "event": "ingest_start",
            "data_root": str(cfg.data_root),
            "manifest_path": str(manifest_path),
        })

        total = 0
        total_sec = 0.0
        bad = 0

        # Write manifest fresh per run (overwrite)
        with open(manifest_path, "w", encoding="utf-8") as man_fp:
            for wav_path in _walk_wavs(cfg.data_root):
                total += 1

                dur, sr, ch = (None, None, None) if cfg.no_duration else _get_wav_meta(wav_path)
                if dur is None:
                    bad += 1

                speaker = _infer_speaker_id(wav_path, cfg.data_root)

                rec = {
                    "id": f"{speaker}::{_safe_relpath(wav_path, cfg.data_root).replace('\\\\', '/')}",
                    "path": str(wav_path),
                    "relpath": _safe_relpath(wav_path, cfg.data_root).replace("\\", "/"),
                    "speaker": speaker,
                    "duration_sec": dur,
                    "sample_rate": sr,
                    "channels": ch,
                    "text": None,  # kept for future metadata join
                }
                _write_jsonl_line(man_fp, rec)

                if dur:
                    total_sec += float(dur)

                # Lightweight audit every N to avoid huge logs
                if total % 500 == 0:
                    _write_jsonl_line(audit_fp, {
                        "ts": _now_iso(),
                        "runId": cfg.run_id,
                        "event": "ingest_progress",
                        "count": total,
                        "bad_duration": bad,
                        "total_duration_sec": round(total_sec, 3),
                    })

        t1 = time.perf_counter()

        summary = {
            "ts": _now_iso(),
            "runId": cfg.run_id,
            "event": "ingest_done",
            "count": total,
            "bad_duration": bad,
            "total_duration_sec": round(total_sec, 3),
            "manifest_path": str(manifest_path),
        }
        _write_jsonl_line(audit_fp, summary)

        _write_jsonl_line(time_fp, {
            "ts": _now_iso(),
            "runId": cfg.run_id,
            "step": "ingest",
            "elapsed_sec": round(t1 - t0, 6),
        })

        if cfg.fail_on_empty and total == 0:
            _write_jsonl_line(err_fp, {
                "ts": _now_iso(),
                "runId": cfg.run_id,
                "event": "ingest_error",
                "error": "No WAV files found under data_root",
                "data_root": str(cfg.data_root),
            })
            return 2

    return 0

def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="NorwegianSpeechBase ingest (stable minimal)")

    # Backward compatibility (ignored)
    ap.add_argument("--root", type=str, default=None, help="(ignored) repo root, use --repo_root instead")
    ap.add_argument("--no_duration", action="store_true", help="(ignored) backward compatibility flag")
    ap.add_argument("--repo_root", type=str, default=None, help="Repository root (defaults to CWD)")
    ap.add_argument("--data_root", type=str, required=True, help="Dataset WAV root to scan (recursive)")
    ap.add_argument("--build_dir", type=str, default=None, help="Build directory (defaults to <repo_root>\\build)")
    ap.add_argument("--logs_dir", type=str, default=None, help="Logs directory (defaults to <repo_root>\\logs\\run_<id>)")
    ap.add_argument("--run_id", type=str, default=None, help="Run identifier (defaults to timestamp)")
    ap.add_argument("--allow_empty", action="store_true", help="Do not fail if no wav found")

    return ap.parse_args(list(argv) if argv is not None else None)

def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    data_root = Path(args.data_root).resolve()

    run_id = args.run_id or _make_run_id()

    build_dir = Path(args.build_dir).resolve() if args.build_dir else (repo_root / "build")
    default_logs = repo_root / "logs" / f"run_{run_id}"
    logs_dir = Path(args.logs_dir).resolve() if args.logs_dir else default_logs

    cfg = IngestConfig(
        repo_root=repo_root,
        data_root=data_root,
        build_dir=build_dir,
        logs_dir=logs_dir,
        run_id=run_id,
        no_duration=args.no_duration,
        fail_on_empty=(not args.allow_empty),
    )

    try:
        return ingest(cfg)
    except KeyboardInterrupt:
        try:
            _ensure_dir(cfg.logs_dir)
            with open(cfg.logs_dir / "errors.jsonl", "a", encoding="utf-8") as err_fp:
                _write_jsonl_line(err_fp, {
                    "ts": _now_iso(),
                    "runId": cfg.run_id,
                    "event": "ingest_interrupt",
                    "error": "KeyboardInterrupt",
                })
        except Exception:
            pass
        return 130
    except Exception as e:
        # Defensive logging
        try:
            _ensure_dir(cfg.logs_dir)
            with open(cfg.logs_dir / "errors.jsonl", "a", encoding="utf-8") as err_fp:
                _write_jsonl_line(err_fp, {
                    "ts": _now_iso(),
                    "runId": cfg.run_id,
                    "event": "ingest_exception",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
        except Exception:
            pass
        return 1

if __name__ == "__main__":
    raise SystemExit(main())




