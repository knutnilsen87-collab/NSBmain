class SLOMonitoring:

    def __init__(self):
        self.latencies = []
        self.errors = []

    def record(self, latency_ms, error=False):
        self.latencies.append(latency_ms)
        self.errors.append(error)

    def avg_latency(self):
        if not self.latencies:
            return 0
        return sum(self.latencies)/len(self.latencies)

    def error_rate(self):
        if not self.errors:
            return 0
        return sum(1 for e in self.errors if e)/len(self.errors)

    def alert_needed(self, latency_threshold, error_threshold):
        return self.avg_latency() > latency_threshold or self.error_rate() > error_threshold
