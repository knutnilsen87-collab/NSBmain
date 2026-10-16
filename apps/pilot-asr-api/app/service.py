from .config import get_settings
from .backends import MockBackend, FasterWhisperBackend

_backend_instance = None


def get_backend():
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    settings = get_settings()

    if settings.backend == "mock":
        _backend_instance = MockBackend(
            model_name=settings.model_name,
            model_device=settings.model_device,
            model_compute_type=settings.model_compute_type,
        )
    elif settings.backend == "faster-whisper":
        _backend_instance = FasterWhisperBackend(
            model_name=settings.model_name,
            model_device=settings.model_device,
            model_compute_type=settings.model_compute_type,
        )
    else:
        raise RuntimeError(f"Unsupported ASR_BACKEND: {settings.backend}")

    if settings.eager_load:
        _backend_instance.load_model()

    return _backend_instance
