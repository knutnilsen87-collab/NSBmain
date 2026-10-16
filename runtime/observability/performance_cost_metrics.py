class PerformanceCostMetrics:

    def __init__(self):
        self.records = []

    def record(self, audio_seconds, compute_seconds):
        cost = compute_seconds / max(audio_seconds,1)
        self.records.append(cost)
        return cost

    def average_cost(self):
        if not self.records:
            return 0
        return sum(self.records) / len(self.records)
