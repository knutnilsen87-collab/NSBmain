class MetricsExporter:

    def __init__(self):
        self.metrics = {}

    def inc(self, name):
        self.metrics[name] = self.metrics.get(name, 0) + 1

    def get(self, name):
        return self.metrics.get(name, 0)
