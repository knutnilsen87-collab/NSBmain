"""Bygger de faste testsettene fra Språkbankens originalfiler.

Kjøres fra prosjektroten der ``dataset/`` ligger::

    python scripts/build_testsets.py --root . --out eval/testsets

Lydstiene i manifestene er relative til prosjektroten, slik at de virker på
alle maskiner med samme mappestruktur. Ingen lyd kopieres.

Testsett:

- ``npsc_test_20170207``: NPSCs offisielle testsplitt for møtet 7. februar 2017
  (den delen av testsplitten som finnes lokalt), med taler og dialekt.
- ``npsc_eval_20170209``: de 582 setningene fra NPSCs eval-splitt som er brukt
  i tidligere målinger, beholdt for sammenligning.
- ``nb_samtale_test``: hele testsplitten i NB Samtale (1 195 segmenter), med
  dialektområde, rettskrivning og overlapp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _write(rows: list[dict], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(data, encoding="utf-8", newline="\n")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def npsc_test(root: Path, date: str = "20170207") -> list[dict]:
    src = root / "dataset/norwegian/NPSC_1/NPSC_2_0_test.jsonl"
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d["meeting_date"] != date:
            continue
        rows.append(
            {
                "id": f"npsc-{d['sentence_id']}",
                "audio": f"dataset/norwegian/NPSC_1/{d['audio']}",
                "text": d["sentence_text"],
                "speaker_id": d["speaker_id"],
                "dialect": d["speaker_dialect"],
                "gender": d["speaker_gender"],
                "standard": "nn" if d["sentence_language_code"].startswith("nn") else "bm",
            }
        )
    return rows


def npsc_eval_legacy(root: Path) -> list[dict]:
    src = root / "data/npsc_eval_clean.jsonl"
    rows = []
    for line in src.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        p = d["audio_filepath"].replace("\\", "/")
        rel = p[p.index("dataset/"):]
        rows.append({"id": Path(rel).stem, "audio": rel, "text": d["text"]})
    return rows


def nb_samtale_test(root: Path) -> list[dict]:
    src = root / "dataset/nb_samtale/metadata.jsonl"
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        fname = d["file_name"].replace("\\", "/")
        if "/test/" not in fname:
            continue
        rows.append(
            {
                "id": f"{d['source_file_id']}_{d['segment_id']}",
                "audio": f"dataset/nb_samtale/{fname}",
                "text": d["transcription"],
                "speaker_id": d["speaker_id"],
                "dialect": {"e": "øst", "w": "vest", "sw": "sørvest", "t": "trøndelag", "n": "nord"}.get(d["dialect"], d["dialect"]),
                "gender": d["gender"],
                "standard": d["orthography"],
                "source_type": d["source_type"],
                "overlap": bool(d["overlap_previous"] or d["overlap_next"]),
                "duration": d["duration"],
            }
        )
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="eval/testsets")
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.out)
    built = {
        "npsc_test_20170207": npsc_test(root),
        "npsc_eval_20170209": npsc_eval_legacy(root),
        "nb_samtale_test": nb_samtale_test(root),
    }
    for name, rows in built.items():
        sha = _write(rows, out / f"{name}.jsonl")
        print(f"{name}: {len(rows)} setninger, sha256 {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
