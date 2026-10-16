from dataclasses import dataclass
from typing import List, Dict

@dataclass
class BenchmarkSample:
    reference: str
    hypothesis: str
    dataset: str

class ModelBenchmarkingPipeline:
    def __init__(self):
        self.results: List[Dict] = []

    def score_sample(self, reference: str, hypothesis: str) -> float:
        ref_words = reference.split()
        hyp_words = hypothesis.split()
        if len(ref_words) == 0:
            return 1.0 if len(hyp_words) == 0 else 0.0
        matches = sum(1 for a, b in zip(ref_words, hyp_words) if a == b)
        return matches / max(len(ref_words), len(hyp_words), 1)

    def run(self, samples: List[BenchmarkSample]) -> Dict:
        scores = []
        per_dataset = {}
        for s in samples:
            score = self.score_sample(s.reference, s.hypothesis)
            scores.append(score)
            per_dataset.setdefault(s.dataset, []).append(score)

        summary = {
            "sample_count": len(samples),
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "datasets": {k: sum(v) / len(v) for k, v in per_dataset.items()}
        }
        self.results.append(summary)
        return summary
