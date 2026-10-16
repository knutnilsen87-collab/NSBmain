import argparse, json, os, shutil, subprocess, sys, time, wave
from pathlib import Path

AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}

def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_jsonl(path: Path):
  with path.open("r", encoding="utf-8") as f:
    for ln in f:
      ln = ln.strip()
      if ln:
        yield json.loads(ln)

def wav_duration(path: Path):
  with wave.open(str(path), "rb") as w:
    sr = w.getframerate()
    frames = w.getnframes()
    ch = w.getnchannels()
    dur = frames / float(sr) if sr else None
  return dur, sr, ch

def have_ffmpeg():
  return shutil.which("ffmpeg") is not None

def run_ffmpeg(inp: Path, out: Path, sr: int):
  # Convert to mono, 16-bit PCM wav, target sr
  cmd = [
    "ffmpeg", "-y",
    "-i", str(inp),
    "-ac", "1",
    "-ar", str(sr),
    "-c:a", "pcm_s16le",
    str(out),
  ]
  p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
  return p.returncode, p.stderr[-4000:]

def copy_or_convert_wav(inp: Path, out: Path, target_sr: int):
  # If it's WAV and already mono+target_sr, copy; else need ffmpeg
  dur, sr, ch = wav_duration(inp)
  if sr == target_sr and ch == 1:
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(inp, out)
    return 0, ""
  if not have_ffmpeg():
    return 10, "ffmpeg not found but wav needs conversion (sr/ch mismatch)."
  return run_ffmpeg(inp, out, target_sr)

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--root", required=True)
  ap.add_argument("--in_manifest", default="data/manifest.jsonl")
  ap.add_argument("--out_dir", default="build/audio_clean")
  ap.add_argument("--out_manifest", default="build/manifest.clean.jsonl")
  ap.add_argument("--sr", type=int, default=16000)
  ap.add_argument("--limit", type=int, default=0)
  args = ap.parse_args()

  root = Path(args.root)
  in_m = root / args.in_manifest
  out_dir = root / args.out_dir
  out_m = root / args.out_manifest

  if not in_m.exists():
    print(json.dumps({"tUtc": utc_now(), "event":"PREPROCESS_FAIL", "error": f"Missing manifest: {in_m}"}))
    return 2

  out_dir.mkdir(parents=True, exist_ok=True)
  out_m.parent.mkdir(parents=True, exist_ok=True)

  ff = have_ffmpeg()

  stats = {
    "tUtc": utc_now(),
    "event": "PREPROCESS_STATS",
    "in_manifest": str(in_m),
    "out_dir": str(out_dir),
    "out_manifest": str(out_m),
    "target_sr": args.sr,
    "ffmpeg": ff,
    "processed": 0,
    "skipped_missing": 0,
    "errors": 0,
    "duration_s_total": 0.0,
  }

  n = 0
  with out_m.open("w", encoding="utf-8") as fout:
    for it in load_jsonl(in_m):
      if args.limit and args.limit > 0 and n >= args.limit:
        break
      n += 1

      rel = it.get("path")
      if not rel:
        continue
      inp = root / rel
      if not inp.exists():
        stats["skipped_missing"] += 1
        continue

      ext = inp.suffix.lower()
      if ext not in AUDIO_EXTS:
        continue

      # Deterministic output name: mirror relative path but force .wav
      out_rel = Path(rel)
      out_rel = out_rel.with_suffix(".wav")
      out_path = out_dir / out_rel
      out_path.parent.mkdir(parents=True, exist_ok=True)

      rc = 0
      err = ""

      try:
        if ext == ".wav":
          rc, err = copy_or_convert_wav(inp, out_path, args.sr)
        else:
          if not ff:
            rc, err = 11, f"ffmpeg not found; cannot convert non-wav: {ext}"
          else:
            rc, err = run_ffmpeg(inp, out_path, args.sr)

        if rc != 0:
          stats["errors"] += 1
          fout.write(json.dumps({
            "path_in": rel,
            "path_out": str(out_path.relative_to(root)),
            "error": err,
            "rc": rc
          }, ensure_ascii=False) + "\n")
          continue

        dur, sr, ch = wav_duration(out_path)
        if isinstance(dur, (int, float)):
          stats["duration_s_total"] += float(dur)

        fout.write(json.dumps({
          "path_in": rel,
          "path_out": str(out_path.relative_to(root)),
          "ext_out": ".wav",
          "sample_rate": sr,
          "channels": ch,
          "duration_s": dur
        }, ensure_ascii=False) + "\n")

        stats["processed"] += 1

      except Exception as e:
        stats["errors"] += 1
        fout.write(json.dumps({
          "path_in": rel,
          "path_out": str(out_path.relative_to(root)),
          "error": str(e)
        }, ensure_ascii=False) + "\n")

  # Write a small report for humans
  rep = root / "reports" / "preprocess_report.json"
  rep.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

  print(json.dumps(stats, ensure_ascii=False))
  return 0 if stats["errors"] == 0 else 5

if __name__ == "__main__":
  raise SystemExit(main())
