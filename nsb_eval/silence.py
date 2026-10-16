"""Lager et testsett uten tale (stillhet og støy) for å måle hallusinasjon.

Hver fil har tom fasit. Alt modellen skriver her er oppdiktet. Settet er
deterministisk (fast frø), så det kan lages på nytt på alle maskiner og gi
samme filer med samme sjekksum.

    python -m nsb_eval.silence --out-dir eval/testsets/silence_v1
"""

from __future__ import annotations

import argparse
import json
import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 16000

# (navn, type, varighet i sekunder, nivå i dBFS)
CLIPS = [
    ("digital_silence_05s", "silence", 5, None),
    ("digital_silence_20s", "silence", 20, None),
    ("white_noise_-60db_10s", "white", 10, -60),
    ("white_noise_-45db_10s", "white", 10, -45),
    ("white_noise_-35db_20s", "white", 20, -35),
    ("brown_noise_-40db_10s", "brown", 10, -40),
    ("brown_noise_-30db_20s", "brown", 20, -30),
    ("hum_50hz_-40db_10s", "hum", 10, -40),
    ("hum_50hz_-30db_20s", "hum", 20, -30),
    ("room_tone_-50db_15s", "room", 15, -50),
    ("room_tone_-40db_25s", "room", 25, -40),
    ("clicks_-30db_10s", "clicks", 10, -30),
]


def _samples(kind: str, seconds: float, level_db: float | None, rng: random.Random) -> list[float]:
    n = int(seconds * SAMPLE_RATE)
    if kind == "silence":
        return [0.0] * n
    amp = 10 ** (level_db / 20.0)
    if kind == "white":
        return [rng.gauss(0.0, amp) for _ in range(n)]
    if kind == "brown":
        out, x = [], 0.0
        for _ in range(n):
            x = 0.995 * x + rng.gauss(0.0, 1.0)
            out.append(x)
        peak = max(abs(v) for v in out) or 1.0
        return [amp * v / peak for v in out]
    if kind == "hum":
        return [
            amp * (math.sin(2 * math.pi * 50 * t / SAMPLE_RATE) + 0.3 * math.sin(2 * math.pi * 150 * t / SAMPLE_RATE))
            + rng.gauss(0.0, amp * 0.05)
            for t in range(n)
        ]
    if kind == "room":
        out, x = [], 0.0
        for t in range(n):
            x = 0.98 * x + rng.gauss(0.0, 1.0)
            out.append(x * 0.1 + 0.2 * math.sin(2 * math.pi * 120 * t / SAMPLE_RATE))
        peak = max(abs(v) for v in out) or 1.0
        return [amp * v / peak for v in out]
    if kind == "clicks":
        out = [rng.gauss(0.0, amp * 0.02) for _ in range(n)]
        for _ in range(int(seconds * 2)):
            pos = rng.randrange(0, n - 40)
            for k in range(40):
                out[pos + k] += amp * math.exp(-k / 6.0) * (1 if k % 2 == 0 else -1)
        return out
    raise ValueError(kind)


def _write_wav(path: Path, samples: list[float]) -> None:
    frames = b"".join(struct.pack("<h", max(-32768, min(32767, round(s * 32767)))) for s in samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)


def build(out_dir: str | Path, seed: int = 20261016) -> Path:
    out = Path(out_dir)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    manifest = out / "manifest.jsonl"
    with open(manifest, "w", encoding="utf-8") as f:
        for name, kind, seconds, level in CLIPS:
            wav = out / "audio" / f"{name}.wav"
            _write_wav(wav, _samples(kind, seconds, level, rng))
            row = {"id": name, "audio": f"audio/{name}.wav", "text": "", "kind": kind, "level_dbfs": level}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=20261016)
    args = ap.parse_args(argv)
    print(build(args.out_dir, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
