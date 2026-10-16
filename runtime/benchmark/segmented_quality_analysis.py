class SegmentedQualityAnalysis:

    def __init__(self):
        self.history = []

    def evaluate(self, dataset_scores):
        result = {}
        for dataset, scores in dataset_scores.items():
            if len(scores) == 0:
                result[dataset] = 0
            else:
                result[dataset] = sum(scores)/len(scores)
        self.history.append(result)
        return result

    def detect_regression(self, previous, current, threshold=0.05):
        regressions = []
        for k in current:
            if k in previous:
                if previous[k] - current[k] > threshold:
                    regressions.append(k)
        return regressions
