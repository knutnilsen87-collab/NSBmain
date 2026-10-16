class StreamingStabilizer:

    def __init__(self, min_repeat=2):
        self.min_repeat = min_repeat
        self.history = []

    def update(self, hypothesis: str) -> str:
        self.history.append(hypothesis)
        if len(self.history) < self.min_repeat:
            return hypothesis

        tail = self.history[-self.min_repeat:]
        if all(x == tail[0] for x in tail):
            return tail[0]

        return self.history[-1]
