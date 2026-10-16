import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.observability.performance_cost_metrics import PerformanceCostMetrics

def test_metrics():
    m = PerformanceCostMetrics()
    m.record(10,20)
    m.record(5,10)
    assert m.average_cost() > 0
