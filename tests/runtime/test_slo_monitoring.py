import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.observability.slo_monitoring import SLOMonitoring

def test_slo():
    s = SLOMonitoring()
    s.record(200,False)
    s.record(500,True)
    assert s.avg_latency() > 0
    assert s.error_rate() > 0
