import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.eval.shadow_inference import ShadowInference

def test_shadow():
    s = ShadowInference()
    s.compare("hei verden","hei verden")
    s.compare("god morgen","god kveld")
    rate = s.agreement_rate()
    assert rate > 0
