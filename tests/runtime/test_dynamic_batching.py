import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.dynamic_batching import DynamicBatcher

def test_batch():
    b = DynamicBatcher(2)
    assert b.add("a") is None
    batch = b.add("b")
    assert len(batch) == 2
