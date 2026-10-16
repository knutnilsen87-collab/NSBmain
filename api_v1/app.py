from fastapi import FastAPI
from pydantic import BaseModel
from pathlib import Path
import subprocess
import json
import uuid
from datetime import datetime, timezone

REPO_ROOT = Path(r"F:\NorwegianSpeechBase")
LATEST_DIR = REPO_ROOT / "logs" / "LATEST"

app = FastAPI(title="NorwegianSpeechBase API v1", version="0.1.0")

class TranscribeRequest(BaseModel):
    text_hint: str | None = None
    reference_mode: bool = False
    operator_id: str | None = None

def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

@app.get("/health")
def health():
    bundle_path = LATEST_DIR / "FBL_STATUS_BUNDLE.txt"
    speak_status_path = LATEST_DIR / "SPEAK_LAST_STATUS.json"
    return {
        "ok": True,
        "service": "NorwegianSpeechBase API v1",
        "bundle_exists": bundle_path.exists(),
        "speak_status_exists": speak_status_path.exists(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }

@app.get("/status/latest")
def status_latest():
    bundle_path = LATEST_DIR / "FBL_STATUS_BUNDLE.txt"
    speak_status_path = LATEST_DIR / "SPEAK_LAST_STATUS.json"
    return {
        "bundle_path": str(bundle_path),
        "speak_status_path": str(speak_status_path),
        "speech_status": load_json(speak_status_path),
        "bundle_preview": bundle_path.read_text(encoding="utf-8") if bundle_path.exists() else None
    }

@app.post("/stt/transcribe")
def transcribe(req: TranscribeRequest):
    script = REPO_ROOT / "nsb-speak.ps1"
    request_id = str(uuid.uuid4())
    arg = req.text_hint or "api request"

    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(script), arg],
        capture_output=True,
        text=True
    )

    speak_status_path = LATEST_DIR / "SPEAK_LAST_STATUS.json"
    bundle_path = LATEST_DIR / "FBL_STATUS_BUNDLE.txt"

    speech_status = load_json(speak_status_path) or {}

    speech_green = (
        speech_status.get("wav_exists") is True and
        speech_status.get("transcribe_ok") is True and
        speech_status.get("hyp_present") is True and
        speech_status.get("blocked_reason") == "none"
    )

    return {
        "ok": completed.returncode == 0,
        "request_id": request_id,
        "run_id": speech_status.get("run_id"),
        "speech_green": speech_green,
        "blocked_reason": speech_status.get("blocked_reason"),
        "reference_mode": req.reference_mode,
        "operator_id": req.operator_id,
        "status_paths": {
            "speak_last_status": str(speak_status_path),
            "bundle": str(bundle_path)
        },
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:]
    }
