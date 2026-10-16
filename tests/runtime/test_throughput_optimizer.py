import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.inference.throughput_optimizer import ThroughputOptimizer

def test_optimizer():
    o = ThroughputOptimizer(2)
    assert o.start()
    assert o.start()
    assert not o.start()
    o.finish()
    assert o.start()
