class GPUBatchMetrics:

    def __init__(self):
        self.gpu_usage = []
        self.batch_sizes = []

    def record(self, gpu_utilization, batch_size):
        self.gpu_usage.append(gpu_utilization)
        self.batch_sizes.append(batch_size)

    def avg_gpu_utilization(self):
        if not self.gpu_usage:
            return 0
        return sum(self.gpu_usage) / len(self.gpu_usage)

    def avg_batch_size(self):
        if not self.batch_sizes:
            return 0
        return sum(self.batch_sizes) / len(self.batch_sizes)
