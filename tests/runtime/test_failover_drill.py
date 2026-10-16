import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.resilience.failover_drill import FailoverDrill

def test_drill():
    f = FailoverDrill()
    f.simulate_failure("regionA")
    f.activate_failover("regionB")
    assert f.drill_success()
