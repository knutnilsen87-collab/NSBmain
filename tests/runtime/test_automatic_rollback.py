import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.release.automatic_rollback import AutomaticRollback

def test_rollback():
    r = AutomaticRollback(0.05)
    assert r.check(0.90,0.80) == "rollback"
    assert r.check(0.90,0.88) == "keep"
