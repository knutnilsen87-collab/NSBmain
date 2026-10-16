import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.benchmark.segmented_quality_analysis import SegmentedQualityAnalysis

def test_segmented_analysis():
    s = SegmentedQualityAnalysis()

    prev = {"clean":[0.9,0.9], "noise":[0.8,0.8]}
    curr = {"clean":[0.9,0.9], "noise":[0.6,0.6]}

    prev_eval = s.evaluate(prev)
    curr_eval = s.evaluate(curr)

    reg = s.detect_regression(prev_eval, curr_eval)

    assert "noise" in reg
