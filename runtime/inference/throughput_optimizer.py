class ThroughputOptimizer:

    def __init__(self, max_parallel=4):
        self.max_parallel = max_parallel
        self.current = 0

    def can_dispatch(self):
        return self.current < self.max_parallel

    def start(self):
        if self.can_dispatch():
            self.current += 1
            return True
        return False

    def finish(self):
        if self.current > 0:
            self.current -= 1
