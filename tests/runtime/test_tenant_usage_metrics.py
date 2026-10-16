import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.billing.tenant_usage_metrics import TenantUsageMetrics

def test_usage_metrics():
    m = TenantUsageMetrics()
    m.record("tenantA",120)
    m.record("tenantA",60)
    report = m.usage_report()
    bill = m.billing_estimate(1.0)

    assert report["tenantA"] == 180
    assert bill["tenantA"] > 0
