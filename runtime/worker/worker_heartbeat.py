import time

class WorkerHeartbeat:

    def __init__(self):
        self.last = None

    def beat(self):
        self.last = time.time()

    def alive(self, timeout=10):
        if self.last is None:
            return False
        return (time.time() - self.last) < timeout
