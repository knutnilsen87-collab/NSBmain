class ShadowInference:

    def __init__(self):
        self.records = []

    def compare(self, production_output, candidate_output):
        same = production_output == candidate_output
        self.records.append({
            "production": production_output,
            "candidate": candidate_output,
            "match": same
        })
        return same

    def agreement_rate(self):
        if not self.records:
            return 0
        matches = sum(1 for r in self.records if r["match"])
        return matches / len(self.records)
