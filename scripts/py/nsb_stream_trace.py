"""Skriver hver oppdatering fra strømmemotoren for en lydfil (feilsøking).

    python scripts/py/nsb_stream_trace.py --model tiny --audio tale.wav --language en
"""

import argparse

import numpy as np
from faster_whisper import decode_audio

from nsb_engine.streaming import FasterWhisperBackend, StreamingRecognizer, join_words, silero_detector


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--language", default="no")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--github", action="store_true", help="skriv som én GitHub-merknad")
    args = ap.parse_args()
    backend = FasterWhisperBackend(args.model, device="cpu", compute_type="int8", language=args.language, beam_size=1)
    a = decode_audio(args.audio, sampling_rate=16000)
    pause = np.zeros(16000, dtype=np.float32)
    audio = np.concatenate([pause] + [x for _ in range(args.repeat) for x in (a, pause)])
    det = silero_detector()
    lines = ["spans " + " ".join(f"{s:.2f}-{e:.2f}" for s, e in det(audio))]
    rec = StreamingRecognizer(backend, detector=det, min_step=1.0)
    for pos in range(0, len(audio), 8000):
        rec.insert_audio(audio[pos:pos + 8000])
        u = rec.process()
        if u.decoded:
            c = " ".join(f"{w.text}[{w.start:.2f}-{w.end:.2f}]" for w in u.committed)
            t = " ".join(f"{w.text}[{w.start:.2f}]" for w in u.tentative)
            lines.append(f"{u.audio_end:5.1f} off={rec.buffer_offset:5.2f} end={rec.committed_end:5.2f} ep={int(u.endpoint)} C: {c} | T: {t}")
    rec.finish()
    lines.append("TEXT " + rec.text())
    if args.github:
        print("::notice::" + "%0A".join(lines))
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
