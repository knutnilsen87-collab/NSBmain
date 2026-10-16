import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.worker.persistent_job_queue import PersistentJobQueue

def test_queue():
    q = PersistentJobQueue("test_queue.json")
    q.push({"id":1})
    job = q.pop()
    assert job["id"] == 1
    Path("test_queue.json").unlink()
