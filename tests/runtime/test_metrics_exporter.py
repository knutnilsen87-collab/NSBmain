import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.telemetry.metrics_exporter import MetricsExporter

def test_metrics():
    m = MetricsExporter()
    m.inc("requests")
    m.inc("requests")
    assert m.get("requests") == 2
