import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.gpu_scheduler import GPUScheduler

def test_gpu_scheduler():
    s = GPUScheduler(2)
    g0 = s.allocate()
    g1 = s.allocate()
    assert g0 == 0
    assert g1 == 1
    s.release(0)
    g2 = s.allocate()
    assert g2 == 0
