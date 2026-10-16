import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.telemetry.runtime_metrics import RuntimeMetrics

def test_metrics():
    m = RuntimeMetrics()
    m.record("decode_time",10)
    m.record("decode_time",20)
    snap = m.snapshot()
    assert snap["decode_time"] == 2
