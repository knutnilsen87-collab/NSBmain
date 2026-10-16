import json
import sys
from pathlib import Path

try:
    import sounddevice as sd
except Exception as e:
    print(json.dumps({"ok": False, "error": f"sounddevice import failed: {e}"}, ensure_ascii=False, indent=2))
    sys.exit(2)

if len(sys.argv) < 2:
    print(json.dumps({"ok": False, "error": "config path required"}, ensure_ascii=False, indent=2))
    sys.exit(2)

config_path = Path(sys.argv[1])
if not config_path.exists():
    print(json.dumps({"ok": False, "error": f"config not found: {config_path}"}, ensure_ascii=False, indent=2))
    sys.exit(2)

cfg = json.loads(config_path.read_text(encoding="utf-8"))
selected_index = cfg.get("selected_index")
fallback_match_contains = cfg.get("fallback_match_contains") or []
candidate_indices = cfg.get("candidate_indices") or []

devices = list(sd.query_devices())

def has_input(d):
    try:
        return (d.get("max_input_channels") or 0) > 0
    except Exception:
        return False

def safe_name(d):
    try:
        return d.get("name") or ""
    except Exception:
        return ""

# 1) Prefer locked selected_index if valid
if selected_index is not None:
    try:
        idx = int(selected_index)
        if 0 <= idx < len(devices) and has_input(devices[idx]):
            print(json.dumps({
                "ok": True,
                "resolved_index": idx,
                "reason": "selected_index_valid",
                "device_name": safe_name(devices[idx])
            }, ensure_ascii=False, indent=2))
            sys.exit(0)
    except Exception:
        pass

# 2) Then candidate_indices
for idx in candidate_indices:
    try:
        idx = int(idx)
        if 0 <= idx < len(devices) and has_input(devices[idx]):
            print(json.dumps({
                "ok": True,
                "resolved_index": idx,
                "reason": "candidate_index_valid",
                "device_name": safe_name(devices[idx])
            }, ensure_ascii=False, indent=2))
            sys.exit(0)
    except Exception:
        pass

# 3) Then fuzzy name match
for idx, d in enumerate(devices):
    if not has_input(d):
        continue
    name = safe_name(d)
    if any(token.lower() in name.lower() for token in fallback_match_contains):
        print(json.dumps({
            "ok": True,
            "resolved_index": idx,
            "reason": "name_match",
            "device_name": name
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

print(json.dumps({
    "ok": False,
    "reason": "no_matching_input_device",
    "selected_index": selected_index,
    "candidate_indices": candidate_indices,
    "fallback_match_contains": fallback_match_contains
}, ensure_ascii=False, indent=2))
sys.exit(3)