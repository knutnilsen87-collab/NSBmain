import argparse, hashlib, json, time
from pathlib import Path

def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_jsonl(path: Path):
  with path.open("r", encoding="utf-8") as f:
    for ln in f:
      ln = ln.strip()
      if ln:
        yield json.loads(ln)

def stable_bucket(key: str) -> int:
  h = hashlib.sha256(key.encode("utf-8")).hexdigest()
  return int(h[:8], 16)  # 0..2^32-1

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", required=True)
  ap.add_argument("--in_manifest", default="build/manifest.clean.jsonl")
  ap.add_argument("--out_dir", default="build/splits")
  ap.add_argument("--train", type=float, default=0.90)
  ap.add_argument("--val", type=float, default=0.08)
  ap.add_argument("--test", type=float, default=0.02)
  ap.add_argument("--report", default="reports/split_report.json")
  args = ap.parse_args()

  # normalize ratios
  s = args.train + args.val + args.test
  if s <= 0:
    print(json.dumps({"tUtc": utc_now(), "event":"SPLIT_FAIL", "error":"Ratios sum to 0"}))
    return 2
  train_r = args.train / s
  val_r   = args.val / s
  test_r  = args.test / s

  root = Path(args.root)
  in_m = root / args.in_manifest
  out_d = root / args.out_dir
  rep = root / args.report
  out_d.mkdir(parents=True, exist_ok=True)
  rep.parent.mkdir(parents=True, exist_ok=True)

  if not in_m.exists():
    print(json.dumps({"tUtc": utc_now(), "event":"SPLIT_FAIL", "error": f"Missing manifest: {in_m}"}))
    return 3

  train_p = out_d / "train.jsonl"
  val_p   = out_d / "val.jsonl"
  test_p  = out_d / "test.jsonl"

  stats = {
    "tUtc": utc_now(),
    "event": "SPLIT_STATS",
    "in_manifest": str(in_m),
    "out_dir": str(out_d),
    "ratios": {"train": train_r, "val": val_r, "test": test_r},
    "counts": {"train": 0, "val": 0, "test": 0},
    "duration_s": {"train": 0.0, "val": 0.0, "test": 0.0},
    "errors": 0,
  }

  def assign(item):
    # Use path_out if present (preprocess), otherwise path (ingest)
    key = item.get("path_out") or item.get("path") or ""
    if not key:
      return "train"
    x = stable_bucket(key) / 4294967296.0  # [0,1)
    if x < train_r:
      return "train"
    if x < train_r + val_r:
      return "val"
    return "test"

  with train_p.open("w", encoding="utf-8") as ftr, val_p.open("w", encoding="utf-8") as fva, test_p.open("w", encoding="utf-8") as fte:
    for it in load_jsonl(in_m):
      try:
        split = assign(it)
        dur = it.get("duration_s", 0.0)
        if isinstance(dur, (int, float)):
          stats["duration_s"][split] += float(dur)

        line = json.dumps(it, ensure_ascii=False)
        if split == "train":
          ftr.write(line + "\n"); stats["counts"]["train"] += 1
        elif split == "val":
          fva.write(line + "\n"); stats["counts"]["val"] += 1
        else:
          fte.write(line + "\n"); stats["counts"]["test"] += 1
      except Exception:
        stats["errors"] += 1

  rep.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(stats, ensure_ascii=False))

  # Fail if no data
  if sum(stats["counts"].values()) == 0:
    return 4
  return 0

if __name__ == "__main__":
  raise SystemExit(main())
