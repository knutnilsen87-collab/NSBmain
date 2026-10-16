class GPUScheduler:

    def __init__(self, gpu_count=1):
        self.gpu_count = gpu_count
        self.busy = [False] * gpu_count

    def allocate(self):
        for i in range(self.gpu_count):
            if not self.busy[i]:
                self.busy[i] = True
                return i
        return None

    def release(self, gpu_id):
        if gpu_id < len(self.busy):
            self.busy[gpu_id] = False
