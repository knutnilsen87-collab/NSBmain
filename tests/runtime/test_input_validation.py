import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.security.input_validation import InputValidator

def test_validation():
    v = InputValidator()
    assert v.validate_audio([1,2,3])
