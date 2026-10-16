class SchedulerLoadBalancer:

    def __init__(self):
        self.workers = []
        self.pointer = 0

    def register(self, worker_id):
        self.workers.append(worker_id)

    def next_worker(self):
        if not self.workers:
            return None
        w = self.workers[self.pointer]
        self.pointer = (self.pointer + 1) % len(self.workers)
        return w
