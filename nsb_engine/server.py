"""Lokal taletjeneste for EVIDA og andre klienter.

Kjører på advokatens egen maskin og lytter bare på 127.0.0.1. Alle kall
unntatt ``/v1/health`` og testsiden krever tilgangsnøkkelen
(``Authorization: Bearer <nøkkel>``, eller ``?token=`` for WebSocket).
Lyd og tekst lagres bare når klienten ber om det og brukeren har samtykket,
og da kryptert, med fast sletting. Alt som gjøres med lagrede økter, føres i
innsynsloggen. Se ``nsb_engine.security`` og ``nsb_engine.sessions``.

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
    ``{"type": "start", "hotwords": "...", "format": "legal"}``. Med
    ``"store": true, "consent": true`` (og valgfritt ``"case_ref"``,
    ``"retention_days"``) lagres lyd og tekst kryptert, og svaret inneholder
    ``session_id`` og ``expires``.
    Avslutt med ``{"type": "end"}``. Tjenesten sender for hver oppdatering::

        {"type": "update", "committed": [ord...], "tentative": [ord...],
         "text": "ferdig tekst, formatert", "tentative_text": "...", "endpoint": false}

    og til slutt ``{"type": "final", "text": ..., "words": [...]}``.
    Et ord er ``{"text", "start", "end", "probability", "uncertain"}``.

``GET /v1/sessions``, ``GET /v1/sessions/{id}``, ``GET /v1/sessions/{id}/audio``,
``PUT /v1/sessions/{id}/transcript``, ``DELETE /v1/sessions/{id}``
    Lagrede økter: liste (uten innhold), tekst, lyd, retting og sletting.

``GET /v1/audit``, ``GET /v1/audit/verify``
    Innsynsloggen og kontroll av at den ikke er endret.

``GET /``
    En enkel testside for diktering i nettleseren (nøkkelen gis i adressen
    etter ``#token=``, som nettleseren ikke sender til tjenesten).
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
from nsb_engine.security import AccessToken, AuditLog, MasterKey, Paths, Vault, default_root
from nsb_engine.sessions import SessionStore
from nsb_engine.streaming import SAMPLE_RATE, StreamingRecognizer, Word, join_words

log = logging.getLogger("nsb_engine")

UNCERTAIN_BELOW = 0.5
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_STORED_SECONDS = 4 * 3600
LOOPBACK = ("127.0.0.1", "localhost", "::1")
PURGE_EVERY_SECONDS = 3600


def _clean_label(value: str | None) -> str | None:
    if not value:
        return None
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_.@")[:64] or None


def word_dict(w: Word, uncertain_below: float = UNCERTAIN_BELOW) -> dict:
    d = asdict(w)
    d["start"], d["end"], d["probability"] = round(w.start, 3), round(w.end, 3), round(w.probability, 3)
    d["uncertain"] = w.probability < uncertain_below
    return d


def _fmt(text: str, mode: str) -> str:
    return format_legal(text) if mode == "legal" else text


def create_app(
    backend,
    *,
    detector_factory=None,
    model_label: str = "",
    device: str = "",
    uncertain_below: float = UNCERTAIN_BELOW,
    data_root: Path | None = None,
    port: int = 8765,
    allowed_origins: list[str] | None = None,
    retention_days: int = 30,
    use_dpapi: bool | None = None,
):
    """Lager FastAPI-appen. ``backend`` deles av alle forbindelser; kall til
    modellen går gjennom én lås, siden det er ett skjermkort."""
    from contextlib import asynccontextmanager

    from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    paths = Paths(data_root or default_root()).ensure()
    token = AccessToken(paths)
    master = MasterKey(paths, use_dpapi=use_dpapi)
    audit = AuditLog(paths, master)
    store = SessionStore(paths, Vault(paths, master), audit, retention_days=retention_days)
    origins = {f"http://{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")} | set(allowed_origins or [])
    hosts = {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")} | {"127.0.0.1", "localhost"}

    @asynccontextmanager
    async def lifespan(_app):
        audit.record("server.started", actor="system", version=__version__, model=model_label, device=device)
        removed = store.purge_expired()
        if removed:
            log.info("slettet %d utløpte økter", len(removed))

        async def purger():
            while True:
                await asyncio.sleep(PURGE_EVERY_SECONDS)
                await asyncio.to_thread(store.purge_expired)

        task = asyncio.create_task(purger())
        try:
            yield
        finally:
            task.cancel()
            audit.record("server.stopped", actor="system")

    app = FastAPI(title="nsb-engine", version=__version__, lifespan=lifespan)
    app.state.paths, app.state.token, app.state.audit, app.state.store = paths, token, audit, store
    app.add_middleware(
        CORSMiddleware, allow_origins=sorted(origins), allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-NSB-User"],
    )
    lock = threading.Lock()

    @app.middleware("http")
    async def check_host(request: Request, call_next):
        # Mot DNS-rebinding: en nettside kan ikke late som den er 127.0.0.1.
        if request.headers.get("host", "") not in hosts:
            return JSONResponse({"detail": "ukjent Host"}, status_code=421)
        return await call_next(request)

    def actor_of(request_headers, user: str | None = None) -> str:
        label = _clean_label(user or request_headers.get("x-nsb-user"))
        return f"token:{token.fingerprint}" + (f"/user:{label}" if label else "")

    def require_token(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        candidate = auth[7:] if auth.lower().startswith("bearer ") else None
        if not token.check(candidate):
            audit.record("auth.denied", actor="unknown", path=request.url.path)
            raise HTTPException(401, "mangler eller feil tilgangsnøkkel", headers={"WWW-Authenticate": "Bearer"})
        return actor_of(request.headers)

    class Locked:
        def transcribe(self, audio, prompt=None, hotwords=None):
            with lock:
                return backend.transcribe(audio, prompt=prompt, hotwords=hotwords)

    shared = Locked()

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "service": "nsb-engine", "version": __version__, "model": model_label, "device": device}

    @app.post("/v1/transcribe")
    async def transcribe(request: Request, hotwords: str | None = None, format: str = "legal",  # noqa: A002
                         actor: str = Depends(require_token)):
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
        audit.record("transcribe", actor=actor, audio_seconds=round(len(audio) / SAMPLE_RATE, 1), stored=False)
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
        origin = ws.headers.get("origin")
        if ws.headers.get("host", "") not in hosts or (origin and origin not in origins):
            audit.record("auth.denied", actor="unknown", path="/v1/stream", origin=origin)
            await ws.close(code=1008)
            return
        if not token.check(ws.query_params.get("token")):
            audit.record("auth.denied", actor="unknown", path="/v1/stream")
            await ws.close(code=1008)
            return
        await ws.accept()
        actor = actor_of(ws.headers, ws.query_params.get("user"))
        rec = StreamingRecognizer(shared, detector=detector_factory() if detector_factory else None)
        mode = "legal"
        started = time.perf_counter()
        keep: dict | None = None  # lagring: {"consent", "case_ref", "retention_days"}
        pcm_parts: list[bytes] = []
        audit.record("stream.started", actor=actor)

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
                if keep is not None:
                    meta = await asyncio.to_thread(
                        store.save, pcm16=b"".join(pcm_parts), words=msg["words"], text=msg["text"], actor=actor,
                        consent=keep["consent"], case_ref=keep["case_ref"], retention_days=keep["retention_days"],
                    )
                    msg["session_id"], msg["expires"] = meta.id, meta.expires
            await ws.send_text(json.dumps(msg, ensure_ascii=False))

        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    if keep is not None:
                        if rec.received < MAX_STORED_SECONDS:
                            pcm_parts.append(msg["bytes"])
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
                        if data.get("store"):
                            if data.get("consent") is not True:
                                await ws.send_text(json.dumps({"type": "error", "detail": "lagring krever samtykke"}))
                                continue
                            days = data.get("retention_days")
                            keep = {"consent": True, "case_ref": _clean_label(data.get("case_ref")),
                                    "retention_days": int(days) if isinstance(days, int) and days > 0 else None}
                    elif data.get("type") == "end":
                        update = await asyncio.to_thread(rec.finish)
                        await send(update, "final")
                        break
        except WebSocketDisconnect:
            pass
        log.info("stream audio=%.1fs wall=%.1fs words=%d", rec.received, time.perf_counter() - started, len(rec.committed))
        audit.record("stream.ended", actor=actor, audio_seconds=round(rec.received, 1), words=len(rec.committed),
                     stored=keep is not None)
        try:
            await ws.close()
        except RuntimeError:
            pass

    def _session(fn, sid, **kw):
        try:
            return fn(sid, **kw)
        except KeyError as e:
            raise HTTPException(404, "ukjent økt") from e

    @app.get("/v1/sessions")
    def list_sessions(actor: str = Depends(require_token)):
        audit.record("sessions.listed", actor=actor)
        return {"sessions": [asdict(m) for m in store.list()], "retention_days": store.retention_days}

    @app.get("/v1/sessions/{sid}")
    def get_session(sid: str, actor: str = Depends(require_token)):
        return {"meta": asdict(_session(store.meta, sid)), **_session(store.transcript, sid, actor=actor)}

    @app.get("/v1/sessions/{sid}/audio")
    def get_audio(sid: str, actor: str = Depends(require_token)):
        return Response(_session(store.audio_wav, sid, actor=actor), media_type="audio/wav",
                        headers={"Cache-Control": "no-store"})

    @app.put("/v1/sessions/{sid}/transcript")
    async def correct_session(sid: str, request: Request, actor: str = Depends(require_token)):
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            raise HTTPException(400, "forventet {\"text\": \"...\"}")
        return asdict(_session(store.correct, sid, text=body["text"], actor=actor))

    @app.delete("/v1/sessions/{sid}", status_code=204)
    def delete_session(sid: str, actor: str = Depends(require_token)):
        _session(store.meta, sid)
        store.delete(sid, actor=actor)
        return Response(status_code=204)

    @app.get("/v1/audit")
    def get_audit(session: str | None = None, actor: str = Depends(require_token)):
        return {"entries": audit.entries(session)}

    @app.get("/v1/audit/verify")
    def verify_audit(actor: str = Depends(require_token)):
        ok, line = audit.verify()
        return {"valid": ok, "first_broken_line": line}

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
    ap.add_argument("--data-dir", help="nøkkel, økter og innsynslogg (standard: brukerens AppData)")
    ap.add_argument("--retention-days", type=int, default=30, help="lagrede økter slettes etter så mange dager")
    ap.add_argument("--allow-origin", action="append", default=[], help="nettadresse som får bruke tjenesten (EVIDA)")
    ap.add_argument("--allow-remote", action="store_true", help="tillat å lytte på andre adresser enn 127.0.0.1 (frarådet)")
    ap.add_argument("--open", action="store_true", help="åpne testsiden i nettleseren")
    ap.add_argument("--no-vad", action="store_true", help="slå av stemmeaktivitetsdeteksjon (frarådet)")
    args = ap.parse_args(argv)
    if args.host not in LOOPBACK and not args.allow_remote:
        ap.error(f"--host {args.host}: tjenesten lytter bare på 127.0.0.1, så lyd ikke kan nås fra nettet. "
                 "Bruk --allow-remote bare hvis du vet hvorfor.")

    import os

    # Ingen nedlastinger eller kall ut: modellen leses fra disk.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    import uvicorn

    from nsb_engine.streaming import FasterWhisperBackend, silero_detector

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    backend = FasterWhisperBackend(args.model, device=args.device, compute_type=args.compute_type, language=args.language)
    app = create_app(backend, detector_factory=None if args.no_vad else silero_detector,
                     model_label=args.label or Path(args.model).parent.name, device=args.device,
                     data_root=Path(args.data_dir) if args.data_dir else None, port=args.port,
                     allowed_origins=args.allow_origin, retention_days=args.retention_days)
    url = f"http://127.0.0.1:{args.port}/#token={app.state.token.value}"
    print(f"nsb-engine kjører på http://127.0.0.1:{args.port}/  (Ctrl+C for å stoppe)")
    print(f"Tilgangsnøkkel: {app.state.paths.token}")
    print(f"Lagrede økter slettes etter {args.retention_days} dager. Innsynslogg: {app.state.paths.audit}")
    if args.open:
        import threading as _t
        import webbrowser

        _t.Timer(3.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
