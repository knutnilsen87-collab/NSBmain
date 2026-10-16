import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.distributed_scheduler import DistributedScheduler

def test_dist():
    s = DistributedScheduler()
    s.register_node("node2")
    s.register_node("node1")
    assert s.leader() == "node1"
