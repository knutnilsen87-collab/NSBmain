import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from runtime.core.batch_inference import BatchInferenceCore, InferenceRequest

class FakeLoader:
    def load(self):
        return object()

class FakeDecoder:
    def decode(self, model, audio_features):
        return {"text": "ok"}

def test_batch_inference_smoke():
    core = BatchInferenceCore(FakeLoader(), FakeDecoder())
    assert core.startup() is True
    req = InferenceRequest(
        audio_features=[1,2,3],
        tenant_id="tenant-a",
        request_id="req-1",
        model_id="model-a"
    )
    res = core.infer(req)
    assert res.status == "PASS"
    assert res.text == "ok"
