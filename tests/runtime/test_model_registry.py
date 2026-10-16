import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.model_registry.model_registry import ModelRegistry

def test_registry():
    r = ModelRegistry()
    r.register("asr","1","/models/asr1")
    assert r.resolve("asr","1") == "/models/asr1"
