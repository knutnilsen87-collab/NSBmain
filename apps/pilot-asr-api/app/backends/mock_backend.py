import os
from typing import Optional, Dict, Any
from .base import TranscriptionBackend


class MockBackend(TranscriptionBackend):
    backend_name = "mock"

    def load_model(self) -> None:
        self.model_loaded = True

    def transcribe_file(self, audio_path: str, language: Optional[str] = None, prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self.model_loaded:
            self.load_model()

        name = os.path.basename(audio_path)
        transcript = f"[MOCK TRANSCRIPT] file={name}; language={language or 'auto'}; prompt={prompt or ''}".strip()
        return {
            "backend": self.backend_name,
            "model_name": self.model_name,
            "audio_source": audio_path,
            "language": language or "auto",
            "transcript": transcript,
            "segments": [],
            "notes": [
                "Mock backend used.",
                "Replace ASR_BACKEND=mock with ASR_BACKEND=faster-whisper after optional dependency install."
            ],
        }
