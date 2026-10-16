import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.gpu_resource_awareness import GPUResourceManager

def test_gpu():
    g = GPUResourceManager(2)
    a = g.allocate()
    b = g.allocate()
    assert a == 0
    assert b == 1
    g.release(0)
    assert g.allocate() == 0
