import argparse, json, time
from pathlib import Path

def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_jsonl(path: Path):
  items = []
  with path.open("r", encoding="utf-8") as f:
    for ln in f:
      ln = ln.strip()
      if not ln: 
        continue
      items.append(json.loads(ln))
  return items

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", required=True)
  ap.add_argument("--manifest", default="data/manifest.jsonl")
  ap.add_argument("--report", default="reports/validate_report.json")
  ap.add_argument("--min_dur", type=float, default=0.20)
  ap.add_argument("--max_dur", type=float, default=30.0)
  ap.add_argument("--allowed_sr", default="16000,44100,48000")
  ap.add_argument("--require_metadata_ratio", type=float, default=0.05, help="min fraction with duration/sample_rate")
  ap.add_argument("--fail_on_invalid", type=int, default=1, help="1 = fail if any invalid, 0 = never fail")
  args = ap.parse_args()

  root = Path(args.root)
  mani = root / args.manifest
  rep  = root / args.report
  rep.parent.mkdir(parents=True, exist_ok=True)

  if not mani.exists():
    print(json.dumps({"tUtc": utc_now(), "event": "VALIDATE_FAIL", "error": f"Missing manifest: {mani}"}))
    return 2

  allowed_sr = set(int(x.strip()) for x in args.allowed_sr.split(",") if x.strip())

  items = load_jsonl(mani)
  total = len(items)

  stats = {
    "tUtc": utc_now(),
    "event": "VALIDATE_STATS",
    "manifest": str(mani),
    "total": total,
    "with_duration": 0,
    "with_sr": 0,
    "with_channels": 0,
    "invalid": 0,
    "warnings": 0,
    "problems": [],
    "rules": {
      "min_dur": args.min_dur,
      "max_dur": args.max_dur,
      "allowed_sr": sorted(list(allowed_sr)),
      "require_metadata_ratio": args.require_metadata_ratio,
      "fail_on_invalid": bool(args.fail_on_invalid),
    },
  }

  for it in items:
    p = it.get("path", "")
    dur = it.get("duration_s", None)
    sr  = it.get("sample_rate", None)
    ch  = it.get("channels", None)

    if isinstance(dur, (int, float)): stats["with_duration"] += 1
    if isinstance(sr, (int, float, int)): stats["with_sr"] += 1
    if isinstance(ch, (int, float, int)): stats["with_channels"] += 1

    # Only validate if metadata present
    bad = []
    warn = []

    if isinstance(dur, (int, float)):
      if dur < args.min_dur: bad.append(f"duration<{args.min_dur}")
      if dur > args.max_dur: bad.append(f"duration>{args.max_dur}")
    elif dur is None:
      warn.append("no_duration")

    if isinstance(sr, int):
      if sr not in allowed_sr: bad.append("sample_rate_not_allowed")
    elif sr is None:
      warn.append("no_sample_rate")

    if isinstance(ch, int):
      if ch not in (1,2): warn.append("channels_unusual")
    elif ch is None:
      warn.append("no_channels")

    if bad:
      stats["invalid"] += 1
      stats["problems"].append({"path": p, "severity": "ERROR", "issues": bad})
    elif warn:
      stats["warnings"] += 1
      # keep warnings list small (avoid huge output)
      if len(stats["problems"]) < 200:
        stats["problems"].append({"path": p, "severity": "WARN", "issues": warn})

  # Enforce that we actually have enough metadata to validate meaningfully
  meta_ratio = (stats["with_duration"] / total) if total else 0.0
  stats["metadata_ratio"] = meta_ratio

  # Write report
  rep.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

  # Emit to stdout for audit append
  print(json.dumps(stats, ensure_ascii=False))

  # Fail conditions
  if total == 0:
    return 3
  if meta_ratio < args.require_metadata_ratio:
    return 4
  if args.fail_on_invalid and stats["invalid"] > 0:
    return 5
  return 0

if __name__ == "__main__":
  raise SystemExit(main())
