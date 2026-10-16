import json
import sys
import time

try:
    import sounddevice as sd
except Exception as e:
    print(json.dumps({"ok": False, "error": f"sounddevice import failed: {e}"}, ensure_ascii=False, indent=2))
    sys.exit(2)

TARGET_TOKENS = ["Mikrofon (Yeti X)", "Yeti X"]
DURATION_SEC = 0.5

def list_input_devices():
    found = []
    for idx, d in enumerate(sd.query_devices()):
        try:
            max_in = int(d.get("max_input_channels", 0) or 0)
            name = str(d.get("name") or "")
        except Exception:
            continue
        if max_in > 0:
            found.append({
                "index": idx,
                "name": name,
                "max_input_channels": max_in,
                "default_samplerate": d.get("default_samplerate"),
                "hostapi": d.get("hostapi"),
            })
    return found

def pick_yetix(devices):
    for token in TARGET_TOKENS:
        for d in devices:
            if token.lower() in d["name"].lower():
                return d
    return None

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
    devices = list_input_devices()
    target = pick_yetix(devices)

    if target is None:
        print(json.dumps({
            "ok": False,
            "error": "Could not find Yeti X input device in current runtime",
            "input_devices": devices
        }, ensure_ascii=False, indent=2))
        sys.exit(3)

    device_index = int(target["index"])
    max_in = int(target.get("max_input_channels", 1) or 1)
    default_sr = int(target.get("default_samplerate") or 48000)

    ordered = [
        (default_sr, min(2, max_in)),
        (default_sr, 1),
        (48000, min(2, max_in)),
        (48000, 1),
        (44100, min(2, max_in)),
        (44100, 1),
    ]

    seen = set()
    combos = []
    for sr, ch in ordered:
        if ch < 1 or ch > max_in:
            continue
        key = (int(sr), int(ch))
        if key not in seen:
            seen.add(key)
            combos.append(key)

    results = [try_combo(device_index, sr, ch) for sr, ch in combos]

    winner = None
    for item in results:
        if item.get("ok"):
            winner = {
                "device_index": item["device_index"],
                "samplerate": item["samplerate"],
                "channels": item["channels"],
            }
            break

    out = {
        "ok": True,
        "target_device": target,
        "input_devices": devices,
        "results": results,
        "winner": winner,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()