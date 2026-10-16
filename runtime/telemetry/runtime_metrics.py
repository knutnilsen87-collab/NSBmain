import time

class RuntimeMetrics:

    def __init__(self):
        self.metrics = {
            "request_latency": [],
            "decode_time": [],
            "worker_queue_depth": [],
            "gpu_utilization": []
        }

    def record(self, name, value):
        if name in self.metrics:
            self.metrics[name].append(value)

    def snapshot(self):
        return {k: len(v) for k,v in self.metrics.items()}
