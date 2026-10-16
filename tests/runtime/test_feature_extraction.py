import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.audio.feature_extraction import FeatureExtractor

def test_feature():
    f = FeatureExtractor()
    val = f.extract([1,2,3])
    assert val > 0
