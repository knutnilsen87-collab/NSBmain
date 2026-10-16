import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.observability.gpu_batch_metrics import GPUBatchMetrics

def test_gpu_batch_metrics():
    m = GPUBatchMetrics()
    m.record(70,4)
    m.record(80,8)
    assert m.avg_gpu_utilization() > 0
    assert m.avg_batch_size() > 0
