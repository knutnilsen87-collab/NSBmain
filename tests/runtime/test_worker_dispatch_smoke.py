import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from runtime.worker.worker_job_dispatch import JobDispatcher

def test_dispatch_smoke():
    d = JobDispatcher()
    job = d.create_job("tenant-a", {"audio": [1,2,3]}, "model-a")
    assert job.status == "QUEUED"
    j2 = d.dispatch()
    assert j2.status == "DISPATCHED"
