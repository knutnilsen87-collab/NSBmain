import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.capacity.tenant_capacity_forecast import TenantCapacityForecast

def test_forecast():
    f = TenantCapacityForecast()
    f.record("tenantA",10)
    f.record("tenantA",20)
    assert f.forecast("tenantA") > 0
