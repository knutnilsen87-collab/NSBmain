import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.eval.model_promotion_gate import ModelPromotionGate

def test_gate():
    g = ModelPromotionGate(0.8)
    assert g.evaluate(0.9)
    assert not g.evaluate(0.5)
