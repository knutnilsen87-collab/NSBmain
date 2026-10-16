from typing import Optional, Dict, Any
from .base import TranscriptionBackend


class FasterWhisperBackend(TranscriptionBackend):
    backend_name = "faster-whisper"

    def __init__(self, model_name: str, model_device: str = "cpu", model_compute_type: str = "int8"):
        super().__init__(model_name, model_device, model_compute_type)
        self._model = None

    def load_model(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install requirements.whisper.optional.txt before enabling ASR_BACKEND=faster-whisper."
            ) from exc

        self._model = WhisperModel(
            self.model_name,
            device=self.model_device,
            compute_type=self.model_compute_type,
        )
        self.model_loaded = True

    def transcribe_file(self, audio_path: str, language: Optional[str] = None, prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self.model_loaded:
            self.load_model()

        segments, info = self._model.transcribe(
            audio_path,
            language=language,
            initial_prompt=prompt,
            vad_filter=True,
        )

        out_segments = []
        text_parts = []

        for segment in segments:
            out_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            })
            text_parts.append(segment.text)

        transcript = " ".join([p.strip() for p in text_parts if p and p.strip()]).strip()

        return {
            "backend": self.backend_name,
            "model_name": self.model_name,
            "audio_source": audio_path,
            "language": getattr(info, "language", language),
            "transcript": transcript,
            "segments": out_segments,
            "notes": [
                "faster-whisper backend used.",
                "Runtime/pipeline remain authoritative for actual execution state."
            ],
        }
