class AutomaticRollback:

    def __init__(self, threshold=0.05):
        self.threshold = threshold

    def check(self, baseline_score, candidate_score):
        if baseline_score - candidate_score > self.threshold:
            return "rollback"
        return "keep"
