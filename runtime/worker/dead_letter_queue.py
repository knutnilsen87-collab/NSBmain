import json
from pathlib import Path

class DeadLetterQueue:

    def __init__(self, path="dead_letter_queue.json"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("[]")

    def push(self, job, reason):
        data = json.loads(self.path.read_text())
        data.append({"job": job, "reason": reason})
        self.path.write_text(json.dumps(data))

    def all(self):
        return json.loads(self.path.read_text())
