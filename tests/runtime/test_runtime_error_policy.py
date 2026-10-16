import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.policy.runtime_error_policy import RuntimePolicy

def test_runtime_policy():
    p = RuntimePolicy()
    assert p.handle_error("GPU_UNAVAILABLE") == "QUEUE_RETRY"
    assert p.handle_error("DECODE_FAILURE") == "FAIL_REQUEST"
    assert p.handle_error("WORKER_TIMEOUT") == "RETRY"
