import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.telemetry.tracing_backend import TracingBackend

def test_trace():
    t = TracingBackend()
    t.record("api_entry","1")
    t.record("decode_complete","1")
    traces = t.get()
    assert len(traces) == 2
