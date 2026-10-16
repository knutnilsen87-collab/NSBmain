import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.release.canary_release import CanaryRelease

def test_canary():
    c = CanaryRelease(50)
    results = [c.route(str(i)) for i in range(100)]
    assert any(results)
    assert not all(results)
