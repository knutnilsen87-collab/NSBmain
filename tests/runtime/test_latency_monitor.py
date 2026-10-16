import sys
from pathlib import Path
import time

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.telemetry.latency_monitor import LatencyMonitor

def test_latency():
    l = LatencyMonitor()
    s = l.start()
    time.sleep(0.01)
    v = l.stop(s)
    assert v > 0
    assert l.avg() > 0
