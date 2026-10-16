import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_capture_config(repo_root: Path):
    cfg_path = repo_root / "config" / "speak_capture.json"
    if not cfg_path.exists():
        return {
            "device_index": 1,
            "samplerate": 44100,
            "channels": 2
        }
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def run_child_transcribe(py_exe: str, wav_path: Path, model_name: str):
    child_code = r"""
import json
import sys
from pathlib import Path

wav_path = Path(sys.argv[1])
model_name = sys.argv[2]

result = {
    "ok": False,
    "engine": None,
    "language": "no",
    "text": "",
    "segments": [],
    "error": None
}

# Try openai-whisper on CPU first
try:
    import whisper
    model = whisper.load_model(model_name)
    r = model.transcribe(str(wav_path), language="no", fp16=False)
    result["ok"] = True
    result["engine"] = "openai_whisper_cpu"
    result["language"] = r.get("language", "no")
    result["text"] = (r.get("text") or "").strip()
    result["segments"] = [
        {
            "start": s.get("start"),
            "end": s.get("end"),
            "text": (s.get("text") or "").strip()
        }
        for s in (r.get("segments") or [])
    ]
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)
except Exception as e:
    result["error"] = f"openai_whisper_cpu_failed: {e}"

# Fallback: faster-whisper on CPU / int8
try:
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(wav_path), language="no")
    segs = []
    texts = []
    for s in segments:
        t = (getattr(s, "text", "") or "").strip()
        segs.append({
            "start": getattr(s, "start", None),
            "end": getattr(s, "end", None),
            "text": t
        })
        if t:
            texts.append(t)
    result["ok"] = True
    result["engine"] = "faster_whisper_cpu_int8"
    result["language"] = getattr(info, "language", "no")
    result["text"] = " ".join(texts).strip()
    result["segments"] = segs
    result["error"] = None
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)
except Exception as e:
    result["error"] = (result["error"] + f" | faster_whisper_cpu_failed: {e}") if result["error"] else f"faster_whisper_cpu_failed: {e}"

print(json.dumps(result, ensure_ascii=False))
raise SystemExit(2)
"""
    cp = subprocess.run(
        [py_exe, "-c", child_code, str(wav_path), model_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return cp.returncode, cp.stdout, cp.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-wav", required=True)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--samplerate", type=int, default=None)
    ap.add_argument("--channels", type=int, default=None)
    ap.add_argument("--model", default="small")
    ap.add_argument("--compute-type", default="float16")  # retained for compatibility
    args = ap.parse_args()

    out_wav = Path(args.out_wav)
    run_dir = out_wav.parent
    repo_root = Path(__file__).resolve().parents[2]

    cfg = load_capture_config(repo_root)
    device = int(args.device if args.device is not None else cfg.get("device_index", 1))
    samplerate = int(args.samplerate if args.samplerate is not None else cfg.get("samplerate", 44100))
    channels = int(args.channels if args.channels is not None else cfg.get("channels", 2))
    seconds = float(args.seconds)
    frames = int(seconds * samplerate)

    result = {
        "status": "starting",
        "text": "",
        "segments": [],
        "device": device,
        "model": args.model,
        "compute_type": args.compute_type,
        "seconds": seconds,
        "language": "no",
        "wav_path": str(out_wav),
        "samplerate_record": samplerate,
        "samplerate_target": samplerate,
        "channels_recorded": channels,
        "engine": None,
        "transcribe_error": None,
        "child_exit_code": None
    }

    try:
        rec = sd.rec(
            frames,
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            device=device
        )
        sd.wait()

        if channels > 1:
            mono = np.mean(rec, axis=1)
        else:
            mono = rec.reshape(-1)

        sf.write(str(out_wav), mono, samplerate)

        result["status"] = "recorded"
        result["wav_exists"] = out_wav.exists()
        result["wav_size"] = out_wav.stat().st_size if out_wav.exists() else 0

        # Write immediately so status survives any later crash
        transcribe_json = run_dir / "transcribe.json"
        write_json(transcribe_json, result)

        py_exe = sys.executable
        child_rc, child_stdout, child_stderr = run_child_transcribe(py_exe, out_wav, args.model)
        result["child_exit_code"] = child_rc

        parsed = None
        if child_stdout and child_stdout.strip():
            last_line = child_stdout.strip().splitlines()[-1]
            try:
                parsed = json.loads(last_line)
            except Exception:
                parsed = None

        if parsed and parsed.get("ok"):
            result["status"] = "transcribed"
            result["engine"] = parsed.get("engine")
            result["language"] = parsed.get("language", "no")
            result["text"] = (parsed.get("text") or "").strip()
            result["segments"] = parsed.get("segments") or []
            result["transcribe_error"] = None
        else:
            result["status"] = "recorded_only"
            if parsed and parsed.get("error"):
                result["transcribe_error"] = parsed.get("error")
            elif child_rc != 0:
                result["transcribe_error"] = f"child_transcribe_failed_exit_{child_rc}"
            else:
                result["transcribe_error"] = "transcription_unavailable"

        write_json(transcribe_json, result)

        print(json.dumps({
            "status": result["status"],
            "device": result["device"],
            "samplerate_record": result["samplerate_record"],
            "channels_recorded": result["channels_recorded"],
            "wav_exists": result.get("wav_exists", False),
            "wav_size": result.get("wav_size", 0),
            "text_len": len(result.get("text", "")),
            "engine": result.get("engine"),
            "transcribe_error": result.get("transcribe_error"),
            "child_exit_code": result.get("child_exit_code")
        }, ensure_ascii=False))
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        write_json(run_dir / "transcribe.json", result)
        raise


if __name__ == "__main__":
    main()
