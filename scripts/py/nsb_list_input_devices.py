import json
import sys

try:
    import sounddevice as sd
except Exception as e:
    print(json.dumps({"ok": False, "error": f"sounddevice import failed: {e}"}, ensure_ascii=False, indent=2))
    sys.exit(2)

devices = []
for idx, d in enumerate(sd.query_devices()):
    try:
        max_in = d.get("max_input_channels", 0)
    except Exception:
        max_in = 0
    if max_in and max_in > 0:
        devices.append({
            "index": idx,
            "name": d.get("name"),
            "hostapi": d.get("hostapi"),
            "max_input_channels": max_in,
            "default_samplerate": d.get("default_samplerate"),
        })

print(json.dumps({
    "ok": True,
    "count": len(devices),
    "devices": devices
}, ensure_ascii=False, indent=2))