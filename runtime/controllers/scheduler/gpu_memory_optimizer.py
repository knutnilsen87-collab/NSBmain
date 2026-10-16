class GPUMemoryOptimizer:

    def __init__(self, total_memory=16000):
        self.total = total_memory
        self.used = 0

    def allocate(self, amount):
        if self.used + amount > self.total:
            return False
        self.used += amount
        return True

    def release(self, amount):
        self.used = max(0, self.used - amount)
