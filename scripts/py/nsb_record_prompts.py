"""Spill inn testsettet for juridisk diktering.

For hver setning i ``prompts.jsonl``: les setningen høyt slik den står under
«SI:», trykk Enter for å starte og Enter igjen for å stoppe. Opptakene lagres
lokalt og skal ikke i git (lyd av stemmer er personopplysninger).

    python scripts/py/nsb_record_prompts.py --speaker knut --device 1

Skriver ``eval/recording/legal_dictation_v1/<taler>/manifest.jsonl`` som kan
måles direkte med ``python -m nsb_eval.runner``. Fasiten for WER er det som ble
sagt (``say``); den ferdig formaterte teksten ligger i ``written``.
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET_DIR = ROOT / "eval" / "recording" / "legal_dictation_v1"


def record_until_enter(samplerate: int, channels: int, device: int | None):
    import numpy as np
    import sounddevice as sd

    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def cb(indata, frames, time, status):  # noqa: ARG001
        q.put(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=channels, device=device, callback=cb):
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        chunks = []
        while not stop.is_set():
            try:
                chunks.append(q.get(timeout=0.1))
            except queue.Empty:
                pass
    audio = np.concatenate(chunks) if chunks else np.zeros((0, channels))
    return audio.mean(axis=1) if channels > 1 else audio[:, 0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--speaker", required=True, help="Kort id for den som leser, f.eks. knut")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--samplerate", type=int, default=44100)
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--start-at", default=None, help="Id å starte fra, f.eks. jd-020")
    args = ap.parse_args(argv)

    import soundfile as sf

    out_dir = SET_DIR / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    done = set()
    if manifest.exists():
        done = {json.loads(line)["id"] for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()}

    prompts = [json.loads(line) for line in (SET_DIR / "prompts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    started = args.start_at is None
    with open(manifest, "a", encoding="utf-8") as f:
        for i, p in enumerate(prompts, start=1):
            started = started or p["id"] == args.start_at
            item_id = f"{args.speaker}-{p['id']}"
            if not started or item_id in done:
                continue
            print(f"\n[{i}/{len(prompts)}] {p['id']} ({p['category']})\nSI: {p['say']}")
            input("Enter for å starte opptak ...")
            print("Tar opp. Enter for å stoppe.")
            audio = record_until_enter(args.samplerate, args.channels, args.device)
            wav = out_dir / f"{p['id']}.wav"
            sf.write(str(wav), audio, args.samplerate)
            row = {
                "id": item_id,
                "audio": wav.relative_to(ROOT).as_posix(),
                "text": p["say"],
                "written": p["text"],
                "category": p["category"],
                "speaker_id": args.speaker,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"Lagret {wav.name} ({len(audio) / args.samplerate:.1f} s)")
    print(f"\nFerdig. Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
