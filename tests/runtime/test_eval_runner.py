import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.eval.evaluation_runner import EvaluationRunner

class FakeDecoder:
    def decode(self,audio):
        return "ok"

def test_eval():
    dataset = [{"audio":[1,2,3],"reference":"ok"}]
    r = EvaluationRunner(FakeDecoder())
    res = r.run(dataset)
    assert res[0]["hyp"] == "ok"
