import os
from functools import lru_cache
from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    service_name: str = os.getenv("ASR_SERVICE_NAME", "pilot-asr-api")
    host: str = os.getenv("ASR_HOST", "0.0.0.0")
    port: int = int(os.getenv("ASR_PORT", "8090"))
    cors_allow_origins: str = os.getenv("ASR_CORS_ALLOW_ORIGINS", "*")
    backend: str = os.getenv("ASR_BACKEND", "mock")  # mock | faster-whisper
    model_name: str = os.getenv("ASR_MODEL_NAME", "mock-small")
    model_device: str = os.getenv("ASR_MODEL_DEVICE", "cpu")
    model_compute_type: str = os.getenv("ASR_MODEL_COMPUTE_TYPE", "int8")
    eager_load: bool = os.getenv("ASR_EAGER_LOAD", "false").lower() == "true"
    temp_dir: str = os.getenv("ASR_TEMP_DIR", "temp")
    max_upload_mb: int = int(os.getenv("ASR_MAX_UPLOAD_MB", "200"))
    supported_upload_extensions: tuple[str, ...] = (
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
        ".ogg",
        ".webm",
        ".mp4",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
