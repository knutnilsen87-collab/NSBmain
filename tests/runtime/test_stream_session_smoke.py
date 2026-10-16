import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from runtime.streaming.session_runtime import StreamingSession, StreamChunk

class FakeDecoder:
    def decode(self, data):
        return "partial-ok"

def test_stream_session_smoke():
    s = StreamingSession(FakeDecoder())
    s.push(StreamChunk([0.1,0.2,0.3]))
    r = s.decode_partial()
    assert r.text == "partial-ok"
    assert r.is_final is False
    f = s.finalize()
    assert f.is_final is True
