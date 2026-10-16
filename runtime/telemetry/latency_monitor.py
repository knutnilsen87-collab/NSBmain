import time

class LatencyMonitor:

    def __init__(self):
        self.records = []

    def start(self):
        return time.time()

    def stop(self, start_time):
        latency = time.time() - start_time
        self.records.append(latency)
        return latency

    def avg(self):
        if not self.records:
            return 0
        return sum(self.records)/len(self.records)
