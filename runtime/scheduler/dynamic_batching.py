class DynamicBatcher:

    def __init__(self, max_batch=4):
        self.max_batch = max_batch
        self.queue = []

    def add(self, item):
        self.queue.append(item)
        if len(self.queue) >= self.max_batch:
            batch = self.queue[:]
            self.queue = []
            return batch
        return None
