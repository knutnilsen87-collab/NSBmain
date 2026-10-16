import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from runtime.streaming.streaming_stabilization import StreamingStabilizer

def test_stream_stabilizer():
    s = StreamingStabilizer(min_repeat=2)
    assert s.update("hei") == "hei"
    assert s.update("hei") == "hei"
    assert s.update("hei der") == "hei der"
