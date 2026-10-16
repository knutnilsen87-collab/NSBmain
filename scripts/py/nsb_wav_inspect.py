import json
import math
import os
import struct
import sys
import wave

def pcm_to_ints(frames: bytes, sampwidth: int):
    if sampwidth == 1:
        # 8-bit PCM is unsigned
        return [b - 128 for b in frames]
    if sampwidth == 2:
        count = len(frames) // 2
        return list(struct.unpack("<{}h".format(count), frames))
    if sampwidth == 4:
        count = len(frames) // 4
        return list(struct.unpack("<{}i".format(count), frames))
    raise ValueError(f"Unsupported sample width: {sampwidth}")

def inspect_wav(path: str):
    out = {
        "wav_path": path,
        "exists": os.path.exists(path),
    }
    if not os.path.exists(path):
        return out

    with wave.open(path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()
        compname = wf.getcompname()
        duration_sec = nframes / float(framerate) if framerate else None
        frames = wf.readframes(nframes)

    ints = pcm_to_ints(frames, sampwidth) if frames else []
    sample_count = len(ints)

    rms = None
    peak = None
    mean_abs = None
    dbfs_rms = None
    zero_ratio = None

    if ints:
        abs_vals = [abs(x) for x in ints]
        peak = max(abs_vals)
        mean_abs = sum(abs_vals) / len(abs_vals)
        squares = [x * x for x in ints]
        rms = math.sqrt(sum(squares) / len(squares))
        zero_ratio = sum(1 for x in ints if x == 0) / len(ints)

        max_possible = float((2 ** (8 * sampwidth - 1)) - 1)
        if rms and max_possible > 0:
            dbfs_rms = 20.0 * math.log10(rms / max_possible)

    out.update({
        "channels": nchannels,
        "sample_width_bytes": sampwidth,
        "sample_rate": framerate,
        "frames": nframes,
        "duration_sec": duration_sec,
        "compression_type": comptype,
        "compression_name": compname,
        "sample_count": sample_count,
        "rms": rms,
        "peak": peak,
        "mean_abs": mean_abs,
        "dbfs_rms": dbfs_rms,
        "zero_ratio": zero_ratio,
    })
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "wav path required"}, ensure_ascii=False, indent=2))
        sys.exit(2)

    result = inspect_wav(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))