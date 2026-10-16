class QueueDecodeLatencyAnalysis:

    def __init__(self):
        self.queue_latencies = []
        self.decode_latencies = []

    def record(self, queue_latency, decode_latency):
        self.queue_latencies.append(queue_latency)
        self.decode_latencies.append(decode_latency)

    def average_queue_latency(self):
        if not self.queue_latencies:
            return 0
        return sum(self.queue_latencies) / len(self.queue_latencies)

    def average_decode_latency(self):
        if not self.decode_latencies:
            return 0
        return sum(self.decode_latencies) / len(self.decode_latencies)

    def queue_pressure_ratio(self):
        dq = self.average_decode_latency()
        if dq == 0:
            return 0
        return self.average_queue_latency() / dq
