import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scaling.worker_autoscaler import WorkerAutoscaler

def test_autoscale():
    a = WorkerAutoscaler(10,2)
    assert a.decision(20) == "scale_up"
    assert a.decision(1) == "scale_down"
    assert a.decision(5) == "stable"
