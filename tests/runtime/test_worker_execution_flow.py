import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.worker.worker_execution_flow import WorkerExecutor, WorkerJob

class FakeDecoder:
    def decode(self,payload):
        return {"text":"ok"}

def test_worker_execution():
    exec = WorkerExecutor(FakeDecoder())
    job = WorkerJob("job1",{"audio":[1,2,3]})
    exec.lease(job)
    res = exec.execute(job)
    assert job.status == "COMPLETED"
    assert res["text"] == "ok"
    assert exec.ack(job) == True
