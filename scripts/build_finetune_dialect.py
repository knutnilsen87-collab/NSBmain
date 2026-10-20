"""Bygger data for første treningsforsøk: dialekt og nynorsk (dialekt_v1).

    python scripts/build_finetune_dialect.py --root . --out data/finetune/dialekt_v1

Trening:
- NB Samtale train (samtaletale, fem dialektområder, bokmål og nynorsk), alle
  segmenter.
- NPSC train fra møtene som finnes lokalt: alle nynorsk-setninger og et
  tilfeldig utvalg bokmål, til ``--npsc-max`` setninger totalt. Holder modellen
  god på formell tale mens den lærer samtale.

Validering (valg av checkpoint, aldri godkjenning):
- ``val.jsonl``: 400 segmenter fra NB Samtale dev (stratifisert på målform) og
  100 fra ``npsc_eval_20170209``.
- ``eval/testsets/nb_samtale_dev.jsonl``: hele dev-splitten, for målestokken.

Utelatt etter reglene i docs/ACCEPTANCE_CRITERIA.md: møtene i de låste
NPSC-settene (7. og 9. februar 2017), alle talere som forekommer i et låst
testsett, og setninger med samme fasittekst (minst fire ord) som et låst
testsett. Hver rad får ``language`` (``no`` eller ``nn``) slik at Whisper
trenes med riktig språktoken.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nsb_eval.normalize import normalize  # noqa: E402

LOCKED_NPSC_MEETINGS = {"20170207", "20170209"}
NB_DIALECT = {"e": "øst", "w": "vest", "sw": "sørvest", "t": "trøndelag", "n": "nord"}


def _jsonl(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _write(rows: list[dict], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(data, encoding="utf-8", newline="\n")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _text_key(text: str) -> str | None:
    norm = normalize(text)
    return norm if len(norm.split()) >= 4 else None


def nb_samtale(root: Path, split: str) -> list[dict]:
    rows = []
    for d in _jsonl(root / "dataset/nb_samtale/metadata.jsonl"):
        fname = d["file_name"].replace("\\", "/")
        if f"/{split}/" not in fname:
            continue
        rows.append({
            "id": f"{d['source_file_id']}_{d['segment_id']}",
            "audio": f"dataset/nb_samtale/{fname}",
            "text": d["transcription"],
            "language": "nn" if d["orthography"] == "nn" else "no",
            "standard": d["orthography"],
            "speaker_id": f"nbs-{d['speaker_id']}",
            "dialect": NB_DIALECT.get(d["dialect"], d["dialect"]),
            "source": "nb_samtale",
            "duration": d["duration"],
        })
    return rows


def npsc_train(root: Path, locked_speakers: set[str]) -> list[dict]:
    base = root / "dataset/norwegian"
    local = {p.name for p in (base / "NPSC_1").iterdir() if p.is_dir()} | {
        p.name for p in (base / "NPSC_2").iterdir() if p.is_dir()}
    rows = []
    for d in _jsonl(base / "NPSC_1/NPSC_2_0_train.jsonl"):
        meeting = d["meeting_date"]
        if meeting in LOCKED_NPSC_MEETINGS or meeting not in local:
            continue
        if d["sentence_language_code"] not in ("nb-NO", "nn-NO"):
            continue
        if f"npsc-{d['speaker_id']}" in locked_speakers:
            continue
        folder = "NPSC_1" if (base / "NPSC_1" / meeting).is_dir() else "NPSC_2"
        nn = d["sentence_language_code"] == "nn-NO"
        rows.append({
            "id": f"npsc-{d['sentence_id']}",
            "audio": f"dataset/norwegian/{folder}/{d['audio']}",
            "text": d["sentence_text"],
            "language": "nn" if nn else "no",
            "standard": "nn" if nn else "bm",
            "speaker_id": f"npsc-{d['speaker_id']}",
            "dialect": d["speaker_dialect"],
            "source": "npsc",
        })
    return rows


def locked_speakers_and_texts(root: Path) -> tuple[set[str], set[str]]:
    speakers, texts = set(), set()
    base = root / "dataset/norwegian/NPSC_1"
    for name in ("NPSC_2_0_test.jsonl", "NPSC_2_0_eval.jsonl"):
        for d in _jsonl(base / name):
            if d["meeting_date"] in LOCKED_NPSC_MEETINGS:
                speakers.add(f"npsc-{d['speaker_id']}")
    for r in nb_samtale(root, "test"):
        speakers.add(r["speaker_id"])
    for name in ("npsc_test_20170207", "npsc_eval_20170209", "nb_samtale_test"):
        for r in _jsonl(root / "eval/testsets" / f"{name}.jsonl"):
            key = _text_key(r["text"])
            if key:
                texts.add(key)
    return speakers, texts


def build(root: Path, out: Path, npsc_max: int = 10000, seed: int = 42) -> dict:
    rng = random.Random(seed)
    locked_speakers, locked_texts = locked_speakers_and_texts(root)
    dropped = Counter()

    def keep(row: dict) -> bool:
        if row["speaker_id"] in locked_speakers:
            dropped["locked_speaker"] += 1
            return False
        if _text_key(row["text"]) in locked_texts:
            dropped["locked_text"] += 1
            return False
        return True

    nbs = [r for r in nb_samtale(root, "train") if keep(r)]
    npsc_all = [r for r in npsc_train(root, locked_speakers) if keep(r)]
    npsc_nn = [r for r in npsc_all if r["language"] == "nn"]
    npsc_bm = [r for r in npsc_all if r["language"] == "no"]
    rng.shuffle(npsc_bm)
    npsc = npsc_nn + npsc_bm[: max(0, npsc_max - len(npsc_nn))]
    train = nbs + npsc
    rng.shuffle(train)

    dev = nb_samtale(root, "dev")
    dev_speakers = {r["speaker_id"] for r in dev}
    leak = [r for r in train if r["speaker_id"] in dev_speakers]
    if leak:  # NB Samtale skal ha adskilte talere; stopp hvis ikke
        raise SystemExit(f"{len(leak)} treningssegmenter har talere fra dev-splitten")
    dev_nn = [r for r in dev if r["language"] == "nn"]
    dev_bm = [r for r in dev if r["language"] == "no"]
    rng.shuffle(dev_nn)
    rng.shuffle(dev_bm)
    val = dev_bm[:280] + dev_nn[:120]
    npsc_val = list(_jsonl(root / "eval/testsets/npsc_eval_20170209.jsonl"))
    rng.shuffle(npsc_val)
    val += [{**r, "language": "no", "source": "npsc_eval"} for r in npsc_val[:100]]

    hashes = {
        "train": _write(train, out / "train.jsonl"),
        "val": _write(val, out / "val.jsonl"),
        "nb_samtale_dev": _write(
            [{k: v for k, v in r.items() if k not in ("language", "source")} for r in dev],
            root / "eval/testsets/nb_samtale_dev.jsonl"),
    }

    def summary(rows):
        return {
            "rows": len(rows),
            "hours": round(sum(r.get("duration") or 0 for r in rows) / 3600, 1) or None,
            "by_source": dict(Counter(r["source"] for r in rows)),
            "by_language": dict(Counter(r["language"] for r in rows)),
            "by_dialect": dict(Counter(r.get("dialect") for r in rows)),
        }

    stats = {
        "seed": seed, "npsc_max": npsc_max, "train": summary(train), "val": summary(val),
        "nb_samtale_dev": len(dev), "dropped": dict(dropped), "locked_speakers": len(locked_speakers),
        "sha256": hashes,
    }
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/finetune/dialekt_v1")
    ap.add_argument("--npsc-max", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    stats = build(Path(args.root), Path(args.out), args.npsc_max, args.seed)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
