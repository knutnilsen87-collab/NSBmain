import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.resilience.multi_region_failover import MultiRegionFailover

def test_failover():
    f = MultiRegionFailover()
    f.register("regionA")
    f.register("regionB")
    assert f.primary() == "regionA"
    assert f.failover() == "regionB"
