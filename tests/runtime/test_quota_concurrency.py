import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.tenant.quota_concurrency import QuotaManager

def test_quota():
    q = QuotaManager(1)
    assert q.acquire()
    assert not q.acquire()
    q.release()
    assert q.acquire()
