"""Lagrede dikteringsøkter: kryptert lyd og tekst med fast sletting.

En økt lagres bare når klienten ber om det og brukeren har samtykket. Hver
økt har en utløpstid; ``purge_expired`` sletter utløpte økter (motoren kjører
den ved oppstart og hver time). Metadata (``<id>.meta.json``) inneholder
ingen lyd eller tekst og ligger ukryptert, slik at utløp kan håndheves uten
å dekryptere noe.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from nsb_engine.security import AuditLog, Paths, Vault, _write_private

SAMPLE_RATE = 16000
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
DEFAULT_RETENTION_DAYS = 30


@dataclass
class SessionMeta:
    id: str
    created: str
    expires: str
    audio_seconds: float
    words: int
    consent: bool
    case_ref: str | None = None  # saksreferanse fra klienten (ikke saksinnhold)
    corrected: str | None = None  # tidspunkt for siste retting


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pcm16_wav(pcm16: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16)
    return buf.getvalue()


class SessionStore:
    def __init__(self, paths: Paths, vault: Vault, audit: AuditLog, *, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.paths, self.vault, self.audit = paths, vault, audit
        self.retention_days = retention_days

    def _meta_path(self, sid: str):
        if not _ID_RE.match(sid or ""):
            raise KeyError(sid)
        return self.paths.sessions / f"{sid}.meta.json"

    def _write_meta(self, meta: SessionMeta) -> None:
        _write_private(self._meta_path(meta.id), json.dumps(asdict(meta), ensure_ascii=False).encode())

    def meta(self, sid: str) -> SessionMeta:
        path = self._meta_path(sid)
        if not path.exists():
            raise KeyError(sid)
        return SessionMeta(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, *, pcm16: bytes, words: list[dict], text: str, actor: str, consent: bool,
             case_ref: str | None = None, retention_days: int | None = None) -> SessionMeta:
        if not consent:
            raise PermissionError("lagring krever samtykke")
        days = min(retention_days or self.retention_days, self.retention_days)  # klienten kan bare korte ned
        sid = secrets.token_urlsafe(18)
        created = _now()
        meta = SessionMeta(
            id=sid, created=created.isoformat(timespec="seconds"),
            expires=(created + timedelta(days=days)).isoformat(timespec="seconds"),
            audio_seconds=round(len(pcm16) / 2 / SAMPLE_RATE, 2), words=len(words), consent=True,
            case_ref=case_ref,
        )
        self.vault.create(sid)
        self.vault.put(sid, "audio", pcm16)
        self.vault.put(sid, "transcript", json.dumps({"text": text, "words": words}, ensure_ascii=False).encode())
        self._write_meta(meta)
        self.audit.record("session.stored", actor=actor, session=sid, audio_seconds=meta.audio_seconds,
                          words=meta.words, expires=meta.expires, case_ref=case_ref)
        return meta

    def list(self) -> list[SessionMeta]:
        out = []
        for p in sorted(self.paths.sessions.glob("*.meta.json")):
            out.append(SessionMeta(**json.loads(p.read_text(encoding="utf-8"))))
        return out

    def transcript(self, sid: str, *, actor: str) -> dict:
        self.meta(sid)
        data = json.loads(self.vault.get(sid, "transcript"))
        if self._has(sid, "corrected"):
            data["corrected"] = json.loads(self.vault.get(sid, "corrected"))
        self.audit.record("session.read", actor=actor, session=sid)
        return data

    def audio_wav(self, sid: str, *, actor: str) -> bytes:
        self.meta(sid)
        wav = _pcm16_wav(self.vault.get(sid, "audio"))
        self.audit.record("session.listened", actor=actor, session=sid)
        return wav

    def correct(self, sid: str, *, text: str, actor: str) -> SessionMeta:
        meta = self.meta(sid)
        original = json.loads(self.vault.get(sid, "transcript"))["text"]
        self.vault.put(sid, "corrected", json.dumps({"text": text}, ensure_ascii=False).encode())
        meta.corrected = _now().isoformat(timespec="seconds")
        self._write_meta(meta)
        changed = sum(1 for a, b in zip(original.split(), text.split(), strict=False) if a != b)
        changed += abs(len(original.split()) - len(text.split()))
        self.audit.record("session.corrected", actor=actor, session=sid, words_changed_approx=changed)
        return meta

    def delete(self, sid: str, *, actor: str, reason: str = "user") -> None:
        self._meta_path(sid)  # validerer id
        self.vault.destroy(sid)
        mp = self._meta_path(sid)
        if mp.exists():
            mp.unlink()
        self.audit.record("session.deleted", actor=actor, session=sid, reason=reason)

    def purge_expired(self, *, now: datetime | None = None) -> list[str]:
        now = now or _now()
        removed = []
        for meta in self.list():
            if datetime.fromisoformat(meta.expires) <= now:
                self.delete(meta.id, actor="system", reason="expired")
                removed.append(meta.id)
        return removed

    def _has(self, sid: str, name: str) -> bool:
        return (self.paths.sessions / f"{sid}.{name}.bin").exists()
