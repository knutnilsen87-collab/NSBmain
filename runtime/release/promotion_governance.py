class PromotionGovernance:

    def __init__(self, min_improvement=0.02):
        self.min_improvement = min_improvement

    def allow_promotion(self, baseline_score, candidate_score):
        improvement = candidate_score - baseline_score
        return improvement >= self.min_improvement
