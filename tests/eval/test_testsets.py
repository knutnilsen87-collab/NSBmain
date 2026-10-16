"""Låser de faste testsettene: innhold, størrelse og sjekksum.

Endres et testsett, må sjekksummen her og i eval/testsets/README.md
oppdateres bevisst. Det hindrer at testsett endres i det stille.
"""

import hashlib
import json
from pathlib import Path

import pytest

from nsb_eval.normalize import normalize

ROOT = Path(__file__).resolve().parents[2]
TESTSETS = ROOT / "eval" / "testsets"

EXPECTED = {
    "npsc_test_20170207.jsonl": (501, "491eab00fdd8f234d4f5b7210ff69fd97980dd7f606b53e7d9cd402c88c4e444"),
    "npsc_eval_20170209.jsonl": (582, "62e68e6abd97d692625c74983c2573390736c93832e3d33f4d5470bdaa5411a0"),
    "nb_samtale_test.jsonl": (1195, "ac4da957b6815498b3a2d7c2f5d0828d8811716a273633e0703d6158da530ac7"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_testset_locked(name):
    path = TESTSETS / name
    count, sha = EXPECTED[name]
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha, f"{name} er endret; oppdater sjekksum bevisst"
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == count
    assert len({r["id"] for r in rows}) == count
    for r in rows:
        assert r["audio"].startswith("dataset/") and "\\" not in r["audio"]
        assert r["text"].strip()


def test_testsets_disjoint():
    seen = {}
    for name in EXPECTED:
        for line in (TESTSETS / name).read_text(encoding="utf-8").splitlines():
            audio = json.loads(line)["audio"]
            assert audio not in seen, f"{audio} finnes i både {seen.get(audio)} og {name}"
            seen[audio] = name


def test_no_unhandled_notation_after_normalization():
    for name in EXPECTED:
        for line in (TESTSETS / name).read_text(encoding="utf-8").splitlines():
            norm = normalize(json.loads(line)["text"])
            assert not any(ch in norm for ch in "\\£%<>_"), norm
