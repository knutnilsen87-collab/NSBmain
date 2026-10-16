import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.release.promotion_governance import PromotionGovernance

def test_promotion():
    g = PromotionGovernance(0.02)
    assert g.allow_promotion(0.80,0.83)
    assert not g.allow_promotion(0.80,0.81)
