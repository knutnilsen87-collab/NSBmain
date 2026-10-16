import time
import uuid

class TraceSpan:

    def __init__(self,name):
        self.name = name
        self.trace_id = str(uuid.uuid4())
        self.start = time.time()
        self.end = None

    def finish(self):
        self.end = time.time()

class RuntimeTracing:

    def start_span(self,name):
        return TraceSpan(name)
