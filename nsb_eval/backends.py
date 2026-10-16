"""Modeller som kan måles. Alle gir samme svarform:

``{"text": str, "duration": float (sekunder lyd), "segments": int}``
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

__all__ = ["Backend", "FasterWhisperBackend", "MockBackend", "make_backend", "wav_duration"]


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, OSError, EOFError):
        return 0.0


class Backend:
    name = "base"

    def describe(self) -> dict:
        return {"backend": self.name}

    def transcribe(self, audio_path: str) -> dict:  # pragma: no cover - grensesnitt
        raise NotImplementedError


class FasterWhisperBackend(Backend):
    """faster-whisper (CTranslate2). Brukes for både Whisper og NB-Whisper.

    Faste innstillinger for sammenlignbare målinger: norsk språk, oppgaven
    «transcribe», strålesøk 5, temperatur 0, ingen kontekst fra forrige
    segment og ingen VAD-filter (VAD skjuler hallusinasjon i stillhet).
    """

    name = "faster-whisper"

    def __init__(
        self,
        model: str,
        device: str = "auto",
        compute_type: str = "default",
        language: str = "no",
        beam_size: int = 5,
        vad_filter: bool = False,
        label: str | None = None,
    ):
        from faster_whisper import WhisperModel  # importeres først her

        self.model_ref = model
        self.label = label or model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = WhisperModel(model, device=device, compute_type=compute_type)

    def describe(self) -> dict:
        import ctranslate2
        import faster_whisper

        return {
            "backend": self.name,
            "model": self.label,
            "model_ref": self.model_ref,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "task": "transcribe",
            "beam_size": self.beam_size,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "vad_filter": self.vad_filter,
            "faster_whisper_version": faster_whisper.__version__,
            "ctranslate2_version": ctranslate2.__version__,
            "cuda_devices": ctranslate2.get_cuda_device_count(),
        }

    def transcribe(self, audio_path: str) -> dict:
        segments, info = self._model.transcribe(
            audio_path,
            language=self.language,
            task="transcribe",
            beam_size=self.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=self.vad_filter,
        )
        parts = [s.text.strip() for s in segments]
        return {
            "text": " ".join(p for p in parts if p),
            "duration": float(getattr(info, "duration", 0.0) or 0.0),
            "segments": len(parts),
        }


class MockBackend(Backend):
    """For tester: svarer med tekst fra en JSON-fil (lydsti -> tekst), eller
    med fasiten når ``echo`` er satt."""

    name = "mock"

    def __init__(self, answers: dict | None = None, label: str = "mock"):
        self.answers = answers or {}
        self.label = label

    @classmethod
    def from_file(cls, path: str, label: str = "mock") -> MockBackend:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), label=label)

    def describe(self) -> dict:
        return {"backend": self.name, "model": self.label}

    def transcribe(self, audio_path: str) -> dict:
        if not Path(audio_path).exists():
            raise FileNotFoundError(audio_path)
        key = Path(audio_path).name
        text = self.answers.get(audio_path, self.answers.get(key, ""))
        return {"text": text, "duration": wav_duration(audio_path), "segments": 1}


def make_backend(kind: str, **kwargs) -> Backend:
    if kind == "faster-whisper":
        return FasterWhisperBackend(**kwargs)
    if kind == "mock":
        answers_file = kwargs.get("answers_file")
        if answers_file:
            return MockBackend.from_file(answers_file, label=kwargs.get("label") or "mock")
        return MockBackend(label=kwargs.get("label") or "mock")
    raise ValueError(f"ukjent backend: {kind}")
