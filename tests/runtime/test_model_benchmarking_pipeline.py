import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from runtime.benchmark.model_benchmarking_pipeline import (
    ModelBenchmarkingPipeline,
    BenchmarkSample,
)

def test_benchmark_pipeline():
    p = ModelBenchmarkingPipeline()
    samples = [
        BenchmarkSample(reference="hei verden", hypothesis="hei verden", dataset="clean"),
        BenchmarkSample(reference="god morgen", hypothesis="god kveld", dataset="clean"),
        BenchmarkSample(reference="test stø y", hypothesis="test stø y", dataset="noise"),
    ]
    res = p.run(samples)
    assert res["sample_count"] == 3
    assert "clean" in res["datasets"]
    assert res["avg_score"] > 0
