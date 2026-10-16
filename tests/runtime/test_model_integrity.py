import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.model_registry.model_integrity import ModelIntegrity

def test_integrity():
    p = Path("tmp_test_file.txt")
    p.write_text("hello")

    h = ModelIntegrity.sha256(p)
    assert ModelIntegrity.verify(p,h)
    p.unlink()
