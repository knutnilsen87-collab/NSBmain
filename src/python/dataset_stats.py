import argparse, json, statistics, time
from pathlib import Path

def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_jsonl(path: Path):
  with path.open("r", encoding="utf-8") as f:
    for ln in f:
      ln = ln.strip()
      if ln:
        yield json.loads(ln)

def summarize(items):
  durs = [it.get("duration_s") for it in items if isinstance(it.get("duration_s"), (int, float))]
  if not durs:
    return {
      "count": len(items),
      "with_duration": 0,
      "total_s": 0.0,
      "total_h": 0.0,
      "min_s": None,
      "max_s": None,
      "median_s": None,
    }

  total = sum(durs)
  return {
    "count": len(items),
    "with_duration": len(durs),
    "total_s": total,
    "total_h": total / 3600.0,
    "min_s": min(durs),
    "max_s": max(durs),
    "median_s": statistics.median(durs),
  }

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", required=True)
  ap.add_argument("--splits", default="build/splits")
  ap.add_argument("--report", default="reports/dataset_stats.json")
  args = ap.parse_args()

  root = Path(args.root)
  splits_dir = root / args.splits
  report = root / args.report
  report.parent.mkdir(parents=True, exist_ok=True)

  if not splits_dir.exists():
    print(json.dumps({"tUtc": utc_now(), "event":"STATS_FAIL", "error": f"Missing splits dir: {splits_dir}"}))
    return 2

  stats = {
    "tUtc": utc_now(),
    "event": "DATASET_STATS",
    "splits_dir": str(splits_dir),
    "splits": {},
  }

  total_all = 0.0

  for name in ("train", "val", "test"):
    p = splits_dir / f"{name}.jsonl"
    if not p.exists():
      stats["splits"][name] = {"error": "missing"}
      continue

    items = list(load_jsonl(p))
    s = summarize(items)
    stats["splits"][name] = s
    total_all += s.get("total_s", 0.0)

  stats["total_all_s"] = total_all
  stats["total_all_h"] = total_all / 3600.0

  report.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(stats, ensure_ascii=False))
  return 0

if __name__ == "__main__":
  raise SystemExit(main())
