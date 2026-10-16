from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

@dataclass
class InferenceRequest:
    audio_features: Any
    tenant_id: str
    request_id: str
    model_id: str

@dataclass
class InferenceResult:
    request_id: str
    tenant_id: str
    model_id: str
    text: str
    latency_ms: float
    status: str

class BatchInferenceCore:
    def __init__(self, model_loader, decoder):
        self.model_loader = model_loader
        self.decoder = decoder
        self.model = None

    def startup(self):
        self.model = self.model_loader.load()
        return self.model is not None

    def infer(self, req: InferenceRequest) -> InferenceResult:
        if self.model is None:
            raise RuntimeError("MODEL_NOT_LOADED")
        t0 = time.perf_counter()
        raw = self.decoder.decode(self.model, req.audio_features)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = raw["text"] if isinstance(raw, dict) and "text" in raw else str(raw)
        return InferenceResult(
            request_id=req.request_id,
            tenant_id=req.tenant_id,
            model_id=req.model_id,
            text=text,
            latency_ms=latency_ms,
            status="PASS",
        )
