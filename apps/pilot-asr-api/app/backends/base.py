from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class TranscriptionBackend(ABC):
    backend_name: str = "base"

    def __init__(self, model_name: str, model_device: str = "cpu", model_compute_type: str = "int8"):
        self.model_name = model_name
        self.model_device = model_device
        self.model_compute_type = model_compute_type
        self.model_loaded = False

    @abstractmethod
    def load_model(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def transcribe_file(self, audio_path: str, language: Optional[str] = None, prompt: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError
