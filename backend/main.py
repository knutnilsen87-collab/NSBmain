from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from pathlib import Path
import time

APP_ROOT = Path(__file__).resolve().parent
MODELS_DIR = APP_ROOT / "models"

app = FastAPI(title="NorwegianSpeechBase TTS")

class TTSRequest(BaseModel):
    text: str
    model: str = "latest"
    format: str = "wav"   # wav | ogg (utvid senere)
    speed: float = 1.0

def list_models():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(MODELS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files if p.is_file()]

def resolve_model(name: str) -> str | None:
    models = list_models()
    if not models:
        return None
    if name == "latest":
        return models[0]
    return name if name in models else None

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/models")
def models():
    return {"models": list_models()}

@app.post("/tts")
def tts(req: TTSRequest):
    t0 = time.time()
    model_name = resolve_model(req.model)
    if model_name is None:
        raise HTTPException(status_code=503, detail="No model checkpoints available yet")

    # TODO: bytt ut stub med ekte VITS-inference når checkpoint er klar.
    # Returnerer minimal WAV (tom lyd) slik at GUI-flyten fungerer.
    wav_bytes = (
        b"RIFF$\x00\x00\x00WAVE"
        b"fmt \x10\x00\x00\x00"
        b"\x01\x00\x01\x00"           # PCM, mono
        b"\x22\x56\x00\x00"           # 22050 Hz
        b"\x44\xac\x00\x00"           # byte rate (dummy)
        b"\x02\x00\x10\x00"           # block align, bits
        b"data\x00\x00\x00\x00"
    )

    latency_ms = int((time.time() - t0) * 1000)
    headers = {"X-Latency-Ms": str(latency_ms), "X-Model": model_name}
    return Response(content=wav_bytes, media_type="audio/wav", headers=headers)
