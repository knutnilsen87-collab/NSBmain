import json
from pathlib import Path

class PersistentJobQueue:

    def __init__(self, path="job_queue.json"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("[]")

    def push(self, job):
        data = json.loads(self.path.read_text())
        data.append(job)
        self.path.write_text(json.dumps(data))

    def pop(self):
        data = json.loads(self.path.read_text())
        if not data:
            return None
        job = data.pop(0)
        self.path.write_text(json.dumps(data))
        return job
