import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo_root))

from runtime.worker.dead_letter_queue import DeadLetterQueue

def test_dlq():
    q = DeadLetterQueue("test_dlq.json")
    q.push({"id":1},"failure")
    items = q.all()
    assert items[0]["job"]["id"] == 1
    Path("test_dlq.json").unlink()
