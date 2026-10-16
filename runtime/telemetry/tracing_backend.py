class TracingBackend:

    def __init__(self):
        self.traces = []

    def record(self, stage, trace_id):
        self.traces.append({
            "trace_id": trace_id,
            "stage": stage
        })

    def get(self):
        return self.traces
