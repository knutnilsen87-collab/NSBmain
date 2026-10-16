import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.scheduler_load_balancer import SchedulerLoadBalancer

def test_lb():
    lb = SchedulerLoadBalancer()
    lb.register("w1")
    lb.register("w2")
    assert lb.next_worker() == "w1"
    assert lb.next_worker() == "w2"
    assert lb.next_worker() == "w1"
