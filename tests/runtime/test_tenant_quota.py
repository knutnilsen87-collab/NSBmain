import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.policy.tenant_quota_enforcement import TenantQuotaManager

def test_quota():
    q = TenantQuotaManager()
    q.set_quota("tenantA",2)
    assert q.check_and_consume("tenantA")
    assert q.check_and_consume("tenantA")
    assert not q.check_and_consume("tenantA")
