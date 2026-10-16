import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.audio.voice_activity_detection import VoiceActivityDetection

def test_vad():
    vad = VoiceActivityDetection()
    assert vad.detect([0.5,0.4,0.3])
    assert not vad.detect([0.001,0.001,0.001])
