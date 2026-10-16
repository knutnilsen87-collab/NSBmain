from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class HealthResponse(APIModel):
    status: str
    backend: str
    model_name: str
    model_loaded: bool
    notes: List[str] = Field(default_factory=list)


class ReadinessResponse(APIModel):
    status: str
    backend: str
    model_name: str
    model_loaded: bool
    ready: bool
    notes: List[str] = Field(default_factory=list)


class APIErrorResponse(APIModel):
    error: str
    detail: str
    request_id: Optional[str] = None
    extra: Optional[dict[str, Any]] = None


class TranscriptionPathRequest(APIModel):
    audio_path: str = Field(..., description="Absolute or relative path to audio file accessible by the API host.")
    language: Optional[str] = None
    prompt: Optional[str] = None


class TranscriptionResponse(APIModel):
    backend: str
    model_name: str
    audio_source: str
    language: Optional[str] = None
    transcript: str
    segments: list = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ModelInfoResponse(APIModel):
    backend: str
    model_name: str
    model_device: str
    model_loaded: bool
    mode: str


class VersionResponse(APIModel):
    service: str
    version: str
    backend: str
    model_name: str
