import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.observability.queue_vs_decode_latency import QueueDecodeLatencyAnalysis

def test_latency_analysis():
    m = QueueDecodeLatencyAnalysis()
    m.record(10,5)
    m.record(8,4)
    assert m.average_queue_latency() > 0
    assert m.average_decode_latency() > 0
    assert m.queue_pressure_ratio() > 0
