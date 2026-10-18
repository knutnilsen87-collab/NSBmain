"""Lokal taletjeneste for EVIDA og andre klienter.

Kjører på advokatens egen maskin og lytter bare på 127.0.0.1. Lyd og tekst
lagres ikke; loggen inneholder bare tidspunkter, varighet og feil.

    python -m nsb_engine.server --model models/benchmark/nb-whisper-large-distil-turbo-beta/ct2_converted

Grensesnitt (versjon 1):

``GET /v1/health``
    Modell, enhet og versjon.

``POST /v1/transcribe``
    Kroppen er en lydfil (wav, mp3, m4a, flac, ogg, webm). Svar: tekst,
    formatert tekst og ord med tider og sikkerhet. Spørreparametre:
    ``hotwords`` (navn og fagord fra saken), ``format`` (``legal`` eller ``none``).

``WS /v1/stream``
    Klienten sender binære meldinger med lyd: 16 kHz, mono, 16-bit PCM
    (little endian). Valgfri første tekstmelding:
    ``{"type": "start", "hotwords": "...", "format": "legal"}``.
    Avslutt med ``{"type": "end"}``. Tjenesten sender for hver oppdatering::

        {"type": "update", "committed": [ord...], "tentative": [ord...],
         "text": "ferdig tekst, formatert", "tentative_text": "...", "endpoint": false}

    og til slutt ``{"type": "final", "text": ..., "words": [...]}``.
    Et ord er ``{"text", "start", "end", "probability", "uncertain"}``.

``GET /``
    En enkel testside for diktering i nettleseren.
"""


import argparse
import asyncio
import io
import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from nsb_engine import __version__
from nsb_engine.legal_format import format_legal
from nsb_engine.streaming import SAMPLE_RATE, StreamingRecognizer, Word, join_words

log = logging.getLogger("nsb_engine")

UNCERTAIN_BELOW = 0.5
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def word_dict(w: Word, uncertain_below: float = UNCERTAIN_BELOW) -> dict:
    d = asdict(w)
    d["start"], d["end"], d["probability"] = round(w.start, 3), round(w.end, 3), round(w.probability, 3)
    d["uncertain"] = w.probability < uncertain_below
    return d


def _fmt(text: str, mode: str) -> str:
    return format_legal(text) if mode == "legal" else text


def create_app(backend, *, detector_factory=None, model_label: str = "", device: str = "", uncertain_below: float = UNCERTAIN_BELOW):
    """Lager FastAPI-appen. ``backend`` deles av alle forbindelser; kall til
    modellen går gjennom én lås, siden det er ett skjermkort."""
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="nsb-engine", version=__version__)
    lock = threading.Lock()

    class Locked:
        def transcribe(self, audio, prompt=None, hotwords=None):
            with lock:
                return backend.transcribe(audio, prompt=prompt, hotwords=hotwords)

    shared = Locked()

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "service": "nsb-engine", "version": __version__, "model": model_label, "device": device}

    @app.post("/v1/transcribe")
    async def transcribe(request: Request, hotwords: str | None = None, format: str = "legal"):  # noqa: A002
        body = await request.body()
        if not body:
            raise HTTPException(400, "tom lydfil")
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "lydfilen er for stor")
        from faster_whisper import decode_audio

        try:
            audio = await asyncio.to_thread(decode_audio, io.BytesIO(body), SAMPLE_RATE)
        except Exception as e:  # noqa: BLE001 - ugyldig lyd fra klienten
            raise HTTPException(415, f"kunne ikke lese lyden: {type(e).__name__}") from e
        t0 = time.perf_counter()
        words = await asyncio.to_thread(shared.transcribe, audio, None, hotwords)
        seconds = time.perf_counter() - t0
        text = join_words(words)
        log.info("transcribe audio=%.1fs processing=%.2fs words=%d", len(audio) / SAMPLE_RATE, seconds, len(words))
        return {
            "text": text,
            "formatted": _fmt(text, format),
            "words": [word_dict(w, uncertain_below) for w in words],
            "audio_seconds": round(len(audio) / SAMPLE_RATE, 3),
            "processing_seconds": round(seconds, 3),
            "model": model_label,
        }

    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket):
        await ws.accept()
        rec = StreamingRecognizer(shared, detector=detector_factory() if detector_factory else None)
        mode = "legal"
        started = time.perf_counter()

        async def send(update, kind="update"):
            text = rec.text()
            msg = {
                "type": kind,
                "committed": [word_dict(w, uncertain_below) for w in update.committed],
                "tentative": [word_dict(w, uncertain_below) for w in update.tentative],
                "text": _fmt(text, mode),
                "tentative_text": join_words(update.tentative),
                "endpoint": update.endpoint,
                "audio_end": round(update.audio_end, 3),
            }
            if kind == "final":
                msg["words"] = [word_dict(w, uncertain_below) for w in rec.committed]
            await ws.send_text(json.dumps(msg, ensure_ascii=False))

        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    pcm = np.frombuffer(msg["bytes"], dtype="<i2").astype(np.float32) / 32768.0
                    rec.insert_audio(pcm)
                    update = await asyncio.to_thread(rec.process)
                    if update.decoded or update.committed:
                        await send(update)
                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        await ws.send_text(json.dumps({"type": "error", "detail": "ugyldig JSON"}))
                        continue
                    if data.get("type") == "start":
                        rec.hotwords = data.get("hotwords") or None
                        mode = data.get("format", "legal")
                    elif data.get("type") == "end":
                        update = await asyncio.to_thread(rec.finish)
                        await send(update, "final")
                        break
        except WebSocketDisconnect:
            pass
        log.info("stream audio=%.1fs wall=%.1fs words=%d", rec.received, time.perf_counter() - started, len(rec.committed))
        try:
            await ws.close()
        except RuntimeError:
            pass

    page = (Path(__file__).parent / "static" / "index.html")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return page.read_text(encoding="utf-8")

    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lokal taletjeneste (nsb-engine)")
    ap.add_argument("--model", required=True, help="mappe med CTranslate2-modell")
    ap.add_argument("--label", default="")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    ap.add_argument("--language", default="no")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-vad", action="store_true", help="slå av stemmeaktivitetsdeteksjon (frarådet)")
    args = ap.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("Tjenesten lytter på %s: andre maskiner på nettet kan nå den.", args.host)

    import uvicorn

    from nsb_engine.streaming import FasterWhisperBackend, silero_detector

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    backend = FasterWhisperBackend(args.model, device=args.device, compute_type=args.compute_type, language=args.language)
    app = create_app(backend, detector_factory=None if args.no_vad else silero_detector,
                     model_label=args.label or Path(args.model).parent.name, device=args.device)
    print(f"nsb-engine kjører: http://{args.host}:{args.port}/  (Ctrl+C for å stoppe)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
