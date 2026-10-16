import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.scheduler.gpu_memory_optimizer import GPUMemoryOptimizer

def test_gpu_mem():
    g = GPUMemoryOptimizer(100)
    assert g.allocate(50)
    assert not g.allocate(60)
    g.release(50)
    assert g.allocate(60)
