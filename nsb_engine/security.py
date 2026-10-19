"""Sikkerhet for den lokale talemotoren.

- ``Paths``: hvor nøkkel, økter og innsynslogg ligger (``%LOCALAPPDATA%\\nsb-engine``
  på Windows, ``~/.local/share/nsb-engine`` ellers).
- ``AccessToken``: tilgangsnøkkelen klienter må sende. Lages ved første start.
- ``MasterKey``: nøkkelen som krypterer øktnøklene. På Windows beskyttes den
  med DPAPI (bundet til Windows-brukeren); ellers ligger den i en fil som bare
  eieren kan lese.
- ``Vault``: krypterer hver økt med sin egen nøkkel (AES-256-GCM). Øktnøkkelen
  lagres kryptert med hovednøkkelen. Når en økt slettes, slettes nøkkelen
  først, så rester av filene på disken ikke kan dekrypteres.
- ``AuditLog``: innsynslogg der hver linje inneholder sjekksummen av den
  forrige. Endres eller fjernes en linje, oppdages det av ``verify``.
  Loggen inneholder aldri lyd eller tekst, bare hva som ble gjort, når og av hvem.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["Paths", "AccessToken", "MasterKey", "Vault", "AuditLog", "default_root"]


def default_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "nsb-engine"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "nsb-engine"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def token(self) -> Path:
        return self.root / "access_token"

    @property
    def master_key(self) -> Path:
        return self.root / "master.key"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions"

    @property
    def audit(self) -> Path:
        return self.root / "audit.jsonl"

    def ensure(self) -> Paths:
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions.mkdir(exist_ok=True)
        _restrict_dir(self.root)
        return self


def _restrict_dir(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o700)


def _write_private(path: Path, data: bytes) -> None:
    """Skriver en fil bare eieren kan lese (POSIX). På Windows arver filen
    rettighetene til brukerens AppData-mappe."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------- DPAPI (Windows)


def _dpapi(data: bytes, protect: bool) -> bytes:  # pragma: no cover - bare Windows
    """CryptProtectData/CryptUnprotectData for gjeldende Windows-bruker."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    dst = Blob()
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(dst)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError(f"DPAPI feilet (Windows-feil {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(dst.pbData, ctypes.c_void_p))


# ---------- Tilgangsnøkkel


class AccessToken:
    """Én tilgangsnøkkel for maskinen. Sammenlignes i konstant tid."""

    def __init__(self, paths: Paths):
        self.path = paths.token
        if self.path.exists():
            self.value = self.path.read_text(encoding="utf-8").strip()
        else:
            self.value = secrets.token_urlsafe(32)
            _write_private(self.path, self.value.encode())

    def check(self, candidate: str | None) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self.value.encode())

    @property
    def fingerprint(self) -> str:
        """Kort, ikke-hemmelig kjennetegn på nøkkelen, til innsynsloggen."""
        return hashlib.sha256(self.value.encode()).hexdigest()[:12]


# ---------- Hovednøkkel og krypterte økter


class MasterKey:
    def __init__(self, paths: Paths, *, use_dpapi: bool | None = None):
        self.path = paths.master_key
        self.use_dpapi = (os.name == "nt") if use_dpapi is None else use_dpapi
        if self.path.exists():
            raw = self.path.read_bytes()
            self.key = _dpapi(raw, protect=False) if self.use_dpapi else raw
        else:
            self.key = secrets.token_bytes(32)
            stored = self.key
            if self.use_dpapi:
                stored = _dpapi(self.key, protect=True)
                if _dpapi(stored, protect=False) != self.key:  # feil heller enn å lagre en nøkkel som ikke kan leses
                    raise OSError("DPAPI ga ikke tilbake samme nøkkel")
            _write_private(self.path, stored)
        if len(self.key) != 32:
            raise ValueError("hovednøkkelen har feil lengde")


class Vault:
    """AES-256-GCM per økt. Filer: ``<id>.key`` (øktnøkkel kryptert med
    hovednøkkelen) og ``<id>.<navn>.bin`` (innhold kryptert med øktnøkkelen)."""

    def __init__(self, paths: Paths, master: MasterKey):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self._aead = AESGCM
        self.dir = paths.sessions
        self.master = AESGCM(master.key)

    def _seal(self, aead, data: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + aead.encrypt(nonce, data, aad)

    def _open(self, aead, blob: bytes, aad: bytes) -> bytes:
        return aead.decrypt(blob[:12], blob[12:], aad)

    def create(self, session_id: str) -> None:
        key = secrets.token_bytes(32)
        _write_private(self.dir / f"{session_id}.key", self._seal(self.master, key, session_id.encode()))

    def _session_key(self, session_id: str):
        path = self.dir / f"{session_id}.key"
        if not path.exists():
            raise KeyError(session_id)
        return self._aead(self._open(self.master, path.read_bytes(), session_id.encode()))

    def put(self, session_id: str, name: str, data: bytes) -> None:
        aad = f"{session_id}/{name}".encode()
        _write_private(self.dir / f"{session_id}.{name}.bin", self._seal(self._session_key(session_id), data, aad))

    def get(self, session_id: str, name: str) -> bytes:
        aad = f"{session_id}/{name}".encode()
        return self._open(self._session_key(session_id), (self.dir / f"{session_id}.{name}.bin").read_bytes(), aad)

    def destroy(self, session_id: str) -> None:
        """Sletter øktnøkkelen først (da kan ingenting dekrypteres), så filene."""
        key = self.dir / f"{session_id}.key"
        if key.exists():
            size = key.stat().st_size
            with open(key, "r+b") as f:  # overskriv før sletting
                f.write(secrets.token_bytes(size))
                f.flush()
                os.fsync(f.fileno())
            key.unlink()
        for p in self.dir.glob(f"{session_id}.*.bin"):
            p.unlink()


# ---------- Innsynslogg


class AuditLog:
    """Kjedet logg (JSON Lines). Hver linje: tid, handling, hvem, økt,
    detaljer uten innhold, sjekksum av forrige linje og av linjen selv.

    Sjekksummen er en HMAC med en nøkkel avledet av hovednøkkelen. Den som
    kan endre filen, kan derfor ikke regne ut nye, gyldige sjekksummer uten
    også å ha hovednøkkelen (på Windows: være logget inn som brukeren)."""

    GENESIS = "0" * 64

    def __init__(self, paths: Paths, master: MasterKey | None = None):
        self.path = paths.audit
        self._key = hmac.new(master.key, b"nsb-engine audit v1", hashlib.sha256).digest() if master else None
        self._lock = threading.Lock()
        self._last = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return self.GENESIS
        last = self.GENESIS
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    def _digest(self, entry: dict) -> str:
        body = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True, ensure_ascii=False).encode()
        if self._key:
            return hmac.new(self._key, body, hashlib.sha256).hexdigest()
        return hashlib.sha256(body).hexdigest()

    def record(self, action: str, *, actor: str, session: str | None = None, **details) -> dict:
        with self._lock:
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "action": action,
                "actor": actor,
                "session": session,
                "details": details,
                "prev": self._last,
            }
            entry["hash"] = self._digest(entry)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._last = entry["hash"]
            return entry

    def entries(self, session: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        return [r for r in rows if session is None or r.get("session") == session]

    def verify(self) -> tuple[bool, int | None]:
        """(gyldig, linjenummer for første brudd)."""
        prev = self.GENESIS
        for i, entry in enumerate(self.entries(), start=1):
            if entry.get("prev") != prev or self._digest(entry) != entry.get("hash"):
                return False, i
            prev = entry["hash"]
        return True, None

