import sys
from pathlib import Path
import time

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.worker.worker_heartbeat import WorkerHeartbeat

def test_heartbeat():
    h = WorkerHeartbeat()
    assert not h.alive()
    h.beat()
    assert h.alive()
    time.sleep(0.01)
    assert h.alive()
