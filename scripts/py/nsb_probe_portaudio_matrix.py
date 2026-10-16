import json
import sys
import time
from pathlib import Path

try:
    import sounddevice as sd
except Exception as e:
    print(json.dumps({"ok": False, "error": f"sounddevice import failed: {e}"}, ensure_ascii=False, indent=2))
    sys.exit(2)

DEVICE_INDEX = 27
DURATION_SEC = 0.5

def safe_query_device(idx):
    d = sd.query_devices(idx, "input")
    return {
        "name": d.get("name"),
        "max_input_channels": d.get("max_input_channels"),
        "default_samplerate": d.get("default_samplerate"),
    }

def try_combo(device_index: int, samplerate: int, channels: int):
    frames = int(samplerate * DURATION_SEC)
    try:
        stream = sd.InputStream(
            device=device_index,
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            blocksize=0
        )
        stream.start()
        data, overflowed = stream.read(frames)
        stream.stop()
        stream.close()
        sample_shape = None
        try:
            sample_shape = list(data.shape)
        except Exception:
            sample_shape = None
        return {
            "ok": True,
            "device_index": device_index,
            "samplerate": samplerate,
            "channels": channels,
            "overflowed": bool(overflowed),
            "sample_shape": sample_shape,
        }
    except Exception as e:
        return {
            "ok": False,
            "device_index": device_index,
            "samplerate": samplerate,
            "channels": channels,
            "error": str(e),
        }

def main():
    device_info = safe_query_device(DEVICE_INDEX)
    default_sr = int(device_info.get("default_samplerate") or 48000)

    combos = []
    ordered = [
        (default_sr, 2),
        (default_sr, 1),
        (48000, 2),
        (48000, 1),
        (44100, 2),
        (44100, 1),
    ]

    seen = set()
    deduped = []
    for sr, ch in ordered:
        key = (int(sr), int(ch))
        if key not in seen:
            seen.add(key)
            deduped.append(key)

    for sr, ch in deduped:
        combos.append(try_combo(DEVICE_INDEX, sr, ch))

    winner = None
    for item in combos:
        if item.get("ok"):
            winner = {
                "device_index": item["device_index"],
                "samplerate": item["samplerate"],
                "channels": item["channels"],
            }
            break

    out = {
        "ok": True,
        "device_index": DEVICE_INDEX,
        "device_info": device_info,
        "results": combos,
        "winner": winner,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()