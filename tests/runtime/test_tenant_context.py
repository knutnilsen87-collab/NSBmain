import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.tenant.tenant_context import TenantContext

def test_context():
    t = TenantContext("tenantA")
    r = t.propagate({})
    assert r["tenant_id"] == "tenantA"
