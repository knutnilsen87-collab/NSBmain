class ModelPromotionGate:

    def __init__(self, threshold=0.85):
        self.threshold = threshold

    def evaluate(self, score):
        return score >= self.threshold
