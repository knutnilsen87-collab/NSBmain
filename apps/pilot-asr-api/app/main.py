import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .models import (
    APIErrorResponse,
    HealthResponse,
    ModelInfoResponse,
    ReadinessResponse,
    TranscriptionPathRequest,
    TranscriptionResponse,
    VersionResponse,
)
from .service import get_backend

settings = get_settings()
app = FastAPI(title=settings.service_name, version="0.1.0")

origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _request_id_from(request: Request | None) -> str | None:
    return getattr(request.state, "request_id", None) if request is not None else None


def _error_response(
    *,
    request: Request | None,
    status_code: int,
    error: str,
    detail: str,
    extra: dict | None = None,
) -> JSONResponse:
    payload = APIErrorResponse(
        error=error,
        detail=detail,
        request_id=_request_id_from(request),
        extra=extra,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(exclude_none=True))


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return _error_response(
        request=request,
        status_code=422,
        error="validation_error",
        detail="Request validation failed.",
        extra={"issues": exc.errors()},
    )


@app.exception_handler(RuntimeError)
async def handle_runtime_error(request: Request, exc: RuntimeError):
    return _error_response(
        request=request,
        status_code=503,
        error="runtime_unavailable",
        detail=str(exc),
    )


def _build_transcription_response(result: dict) -> TranscriptionResponse:
    return TranscriptionResponse(**result)


def _ensure_audio_path_exists(audio_path: str, request: Request) -> None:
    if not os.path.exists(audio_path):
        raise HTTPException(
            status_code=404,
            detail=APIErrorResponse(
                error="audio_not_found",
                detail=f"Audio path not found: {audio_path}",
                request_id=_request_id_from(request),
            ).model_dump(exclude_none=True),
        )


def _validate_upload_filename(file: UploadFile, request: Request) -> str:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if not suffix:
        raise HTTPException(
            status_code=400,
            detail=APIErrorResponse(
                error="missing_extension",
                detail="Uploaded file must include a supported audio filename extension.",
                request_id=_request_id_from(request),
            ).model_dump(exclude_none=True),
        )
    if suffix not in settings.supported_upload_extensions:
        raise HTTPException(
            status_code=415,
            detail=APIErrorResponse(
                error="unsupported_media_type",
                detail="Unsupported audio file extension.",
                request_id=_request_id_from(request),
                extra={"supported_extensions": list(settings.supported_upload_extensions), "received_extension": suffix},
            ).model_dump(exclude_none=True),
        )
    return suffix


def _write_upload_to_temp(file: UploadFile, suffix: str, request: Request) -> str:
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total_bytes = 0

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=temp_dir) as tmp:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                tmp.close()
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=APIErrorResponse(
                        error="file_too_large",
                        detail=f"Upload exceeds the configured limit of {settings.max_upload_mb} MB.",
                        request_id=_request_id_from(request),
                        extra={"max_upload_mb": settings.max_upload_mb},
                    ).model_dump(exclude_none=True),
                )
            tmp.write(chunk)

    if total_bytes == 0:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail=APIErrorResponse(
                error="empty_upload",
                detail="Uploaded file is empty.",
                request_id=_request_id_from(request),
            ).model_dump(exclude_none=True),
        )
    return tmp.name


@app.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    backend = get_backend()
    notes = []
    if backend.backend_name == "mock":
        notes.append("Mock backend active. Pilot integration can proceed, but transcripts are synthetic.")

    return HealthResponse(
        status="ok",
        backend=backend.backend_name,
        model_name=backend.model_name,
        model_loaded=backend.model_loaded,
        notes=notes,
    )


@app.get("/v1/readiness", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    backend = get_backend()
    notes = []
    ready = backend.model_loaded

    if not backend.model_loaded:
        try:
            backend.load_model()
            ready = True
        except Exception as exc:
            ready = False
            notes.append(str(exc))

    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        backend=backend.backend_name,
        model_name=backend.model_name,
        model_loaded=backend.model_loaded,
        ready=ready,
        notes=notes,
    )


@app.get("/v1/models", response_model=ModelInfoResponse)
def models() -> ModelInfoResponse:
    backend = get_backend()
    return ModelInfoResponse(
        backend=backend.backend_name,
        model_name=backend.model_name,
        model_device=backend.model_device,
        model_loaded=backend.model_loaded,
        mode="read-write-api / read-only-artifact-policy-compatible",
    )


@app.post(
    "/v1/transcriptions/path",
    response_model=TranscriptionResponse,
    responses={404: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def transcribe_path(request: TranscriptionPathRequest, http_request: Request) -> TranscriptionResponse:
    backend = get_backend()
    _ensure_audio_path_exists(request.audio_path, http_request)

    result = backend.transcribe_file(
        audio_path=request.audio_path,
        language=request.language,
        prompt=request.prompt,
    )
    return _build_transcription_response(result)


@app.post(
    "/v1/transcriptions/upload",
    response_model=TranscriptionResponse,
    responses={
        400: {"model": APIErrorResponse},
        413: {"model": APIErrorResponse},
        415: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def transcribe_upload(http_request: Request, file: UploadFile = File(...)) -> TranscriptionResponse:
    backend = get_backend()
    suffix = _validate_upload_filename(file, http_request)
    temp_path = _write_upload_to_temp(file, suffix, http_request)

    try:
        result = backend.transcribe_file(audio_path=temp_path)
        result["audio_source"] = f"upload:{file.filename or Path(temp_path).name}"
        return _build_transcription_response(result)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


@app.get("/v1/version", response_model=VersionResponse)
def version() -> VersionResponse:
    backend = get_backend()
    return VersionResponse(service=settings.service_name, version="0.1.0", backend=backend.backend_name, model_name=backend.model_name)


@app.get("/health")
def health_alias() -> dict:
    return {"status": "ok"}


@app.get("/version", response_model=VersionResponse)
def version_alias() -> VersionResponse:
    backend = get_backend()
    return VersionResponse(service=settings.service_name, version="0.1.0", backend=backend.backend_name, model_name=backend.model_name)
