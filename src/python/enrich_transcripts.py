import argparse, json, re, time
from pathlib import Path

def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def norm_key(s: str) -> str:
  # normalize path-ish id into a stable matching key
  s = s.strip().replace("\\", "/")
  s = s.split("/")[-1]  # basename
  s = re.sub(r"\.[a-z0-9]+$", "", s, flags=re.IGNORECASE)  # drop extension
  return s.lower()

def load_meta(meta_path: Path):
  # norwegian_meta: "something.wav|text..." OR "utt_xxx|text..."
  m = {}
  total = 0
  dup = 0
  bad = 0
  with meta_path.open("r", encoding="utf-8", errors="replace") as f:
    for ln in f:
      ln = ln.strip()
      if not ln or ln.startswith("#"):
        continue
      total += 1
      if "|" not in ln:
        bad += 1
        continue
      k, txt = ln.split("|", 1)
      k2 = norm_key(k)
      txt = txt.strip()
      if not txt:
        bad += 1
        continue
      if k2 in m:
        dup += 1
        # keep first (deterministic)
        continue
      m[k2] = txt
  return m, {"meta_total_lines": total, "meta_bad": bad, "meta_dups": dup, "meta_unique": len(m)}

def load_jsonl(p: Path):
  with p.open("r", encoding="utf-8") as f:
    for ln in f:
      ln = ln.strip()
      if ln:
        yield json.loads(ln)

def write_jsonl(p: Path, items):
  p.parent.mkdir(parents=True, exist_ok=True)
  with p.open("w", encoding="utf-8") as f:
    for it in items:
      f.write(json.dumps(it, ensure_ascii=False) + "\n")

def pick_candidate_keys(item):
  # Try several candidates (path_out, path_in, path) -> stem
  cands = []
  for k in ("path_out", "path_in", "path"):
    v = item.get(k)
    if isinstance(v, str) and v.strip():
      cands.append(norm_key(v))
  # Also try basename only (already) and any "id" field if present
  v = item.get("id")
  if isinstance(v, str) and v.strip():
    cands.append(norm_key(v))
  # de-dup preserving order
  out = []
  seen = set()
  for x in cands:
    if x and x not in seen:
      out.append(x); seen.add(x)
  return out

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", required=True)
  ap.add_argument("--meta", required=True)
  ap.add_argument("--splits_dir", default="build/splits")
  ap.add_argument("--out_dir", default="build/splits_labeled")
  ap.add_argument("--field", default="text")
  ap.add_argument("--report", default="reports/enrich_report.json")
  args = ap.parse_args()

  root = Path(args.root)
  meta_path = Path(args.meta)
  splits_dir = root / args.splits_dir
  out_dir = root / args.out_dir
  report_path = root / args.report
  report_path.parent.mkdir(parents=True, exist_ok=True)

  if not meta_path.exists():
    print(json.dumps({"tUtc": utc_now(), "event":"ENRICH_FAIL", "error": f"Missing meta file: {meta_path}"} , ensure_ascii=False))
    return 2
  if not splits_dir.exists():
    print(json.dumps({"tUtc": utc_now(), "event":"ENRICH_FAIL", "error": f"Missing splits dir: {splits_dir}"} , ensure_ascii=False))
    return 3

  meta, meta_stats = load_meta(meta_path)

  overall = {
    "tUtc": utc_now(),
    "event": "ENRICH_STATS",
    "meta_path": str(meta_path),
    "splits_dir": str(splits_dir),
    "out_dir": str(out_dir),
    "field": args.field,
    **meta_stats,
    "splits": {},
    "total_items": 0,
    "total_labeled": 0,
    "total_unlabeled": 0,
  }

  for split in ("train", "val", "test"):
    inp = splits_dir / f"{split}.jsonl"
    if not inp.exists():
      overall["splits"][split] = {"missing": True}
      continue

    items = list(load_jsonl(inp))
    labeled = 0
    unlabeled = 0

    for it in items:
      keys = pick_candidate_keys(it)
      txt = None
      for k in keys:
        if k in meta:
          txt = meta[k]
          break
      if txt:
        it[args.field] = txt
        labeled += 1
      else:
        unlabeled += 1

    outp = out_dir / f"{split}.jsonl"
    write_jsonl(outp, items)

    overall["splits"][split] = {
      "in": str(inp),
      "out": str(outp),
      "count": len(items),
      "labeled": labeled,
      "unlabeled": unlabeled,
      "labeled_ratio": (labeled / len(items)) if items else 0.0,
    }
    overall["total_items"] += len(items)
    overall["total_labeled"] += labeled
    overall["total_unlabeled"] += unlabeled

  report_path.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
  print(json.dumps(overall, ensure_ascii=False))
  return 0 if overall["total_labeled"] > 0 else 5

if __name__ == "__main__":
  raise SystemExit(main())
