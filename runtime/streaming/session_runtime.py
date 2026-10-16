from dataclasses import dataclass
from typing import List, Optional
import time

@dataclass
class StreamChunk:
    data: List[float]

@dataclass
class PartialResult:
    text: str
    is_final: bool
    latency_ms: float

class StreamingSession:
    def __init__(self, decoder):
        self.decoder = decoder
        self.buffer = []
        self.created_at = time.time()

    def push(self, chunk: StreamChunk):
        self.buffer.extend(chunk.data)

    def decode_partial(self) -> Optional[PartialResult]:
        if len(self.buffer) == 0:
            return None
        t0 = time.perf_counter()
        text = self.decoder.decode(self.buffer)
        latency = (time.perf_counter() - t0) * 1000.0
        return PartialResult(text=text, is_final=False, latency_ms=latency)

    def finalize(self) -> PartialResult:
        t0 = time.perf_counter()
        text = self.decoder.decode(self.buffer)
        latency = (time.perf_counter() - t0) * 1000.0
        self.buffer = []
        return PartialResult(text=text, is_final=True, latency_ms=latency)
