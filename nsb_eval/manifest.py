"""Lasting av testsett-manifester.

Et manifest er JSONL med én setning per linje. Feltene som leses:

- lyd: ``audio`` | ``audio_filepath`` | ``path`` | ``audio_path``
- fasit: ``text`` | ``sentence_text`` | ``transcript`` (tom streng er lov,
  for eksempel i stillhetssettet)
- id: ``id`` | ``sentence_id`` (ellers lydstien)
- ``verified: false`` betyr at fasiten ikke er kontrollert mot opptaket ennå.
  Slike rader hoppes over, så uverifiserte fasiter aldri havner i en måling.

Relative lydstier løses mot ``audio_root``. Gamle absolutte Windows-stier kan
skrives om med ``path_map`` (for eksempel ``F:\\NorwegianSpeechBase`` ->
``F:\\prosjekter_MAIN\\NorwegianSpeechBase``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

__all__ = ["Item", "file_sha256", "load_manifest", "resolve_audio_path"]

_AUDIO_KEYS = ("audio", "audio_filepath", "path", "audio_path")
_TEXT_KEYS = ("text", "sentence_text", "transcript")
_ID_KEYS = ("id", "sentence_id")


@dataclass
class Item:
    id: str
    audio: str
    text: str
    meta: dict = field(default_factory=dict)


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _first(row: dict, keys: tuple) -> object:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def resolve_audio_path(raw: str, audio_root: str | Path | None, path_map: dict | None) -> str:
    """Gir en brukbar sti for lydfilen.

    Rekkefølge: skriv om prefiks etter ``path_map``; er stien relativ, legg den
    under ``audio_root``. Både ``/`` og ``\\`` godtas som skilletegn.
    """
    p = raw
    for old, new in (path_map or {}).items():
        if p.lower().startswith(old.lower()):
            p = new + p[len(old):]
            break
    is_windows_abs = PureWindowsPath(p).is_absolute() or (len(p) > 1 and p[1] == ":")
    if not is_windows_abs and not Path(p).is_absolute() and audio_root is not None:
        parts = p.replace("\\", "/").split("/")
        return str(Path(audio_root).joinpath(*parts))
    return p


def load_manifest(
    path: str | Path,
    audio_root: str | Path | None = None,
    path_map: dict | None = None,
) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("verified") is False:
                continue
            audio = _first(row, _AUDIO_KEYS)
            if not audio:
                raise ValueError(f"{path}:{lineno}: mangler lydsti")
            text = _first(row, _TEXT_KEYS)
            if text is None:
                raise ValueError(f"{path}:{lineno}: mangler fasittekst")
            item_id = str(_first(row, _ID_KEYS) or audio)
            if item_id in seen:
                raise ValueError(f"{path}:{lineno}: dobbel id {item_id}")
            seen.add(item_id)
            meta = {k: v for k, v in row.items() if k not in _AUDIO_KEYS + _TEXT_KEYS + _ID_KEYS}
            items.append(
                Item(
                    id=item_id,
                    audio=resolve_audio_path(str(audio), audio_root, path_map),
                    text=str(text),
                    meta=meta,
                )
            )
    return items
