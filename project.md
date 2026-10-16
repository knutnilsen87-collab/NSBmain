# NorwegianSpeechBase - MASTER PROJECT CONTRACT

**Project:** NorwegianSpeechBase
**Component:** Whisper ASR Training (openai/whisper-medium)
**Primary Environment:** Windows 11 + PowerShell 7 + RTX 4080
**Last validated:** 2025-12-29 (Europe/Oslo)

---

## 1. Purpose of This Document

This document is the **single source of truth** for training Whisper on NorwegianSpeechBase.

If you are new to the project, you should be able to:
- Understand *exactly* how training works
- Know what is allowed vs forbidden
- Recover from failures without guesswork
- Avoid all known foot-guns

If something here conflicts with code, **this document wins**.

---

## 2. High-Level Architecture

**Key principle:** *Lazy, fault-tolerant, resumable training*.

Pipeline:

```
JSONL (paths + text)
   ↓
Dataset.from_list()
   ↓
set_transform(prepare)   ← LAZY (no map, no Arrow cache)
   ↓
PyTorch DataLoader (num_workers=0)
   ↓
Whisper Trainer
   ↓
Incremental checkpoints
```

Absolutely **no full-dataset preprocessing** is allowed.

---

## 3. Hardware & Environment Contract

### Hardware
- CPU: i9-class
- RAM: ≥ 32 GB
- GPU: RTX 4080 (16 GB VRAM)

### Software
- OS: Windows (WDDM)
- Python: 3.13.x (venv required)
- PyTorch: CUDA-enabled
- transformers / datasets / accelerate

### Mandatory Rules
- `.venv` **must** be activated
- `torch.cuda.is_available()` **must** be true
- Training must run in PowerShell 7

---

## 4. Data Contract

### JSONL schema
Each line **must** contain:

```json
{
  "path": "ABSOLUTE_PATH_TO_WAV",
  "text": "normalized UTF-8 transcription"
}
```

### Audio assumptions
- WAV format
- Any sample rate (resampled on-the-fly to 16 kHz)
- Mono or stereo
- Some files **will be corrupt or missing** (this is expected)

### Dataset size
- ~360k training samples

---

## 5. Invariants (DO NOT BREAK)

These are **non-negotiable**:

- Training uses `Dataset.set_transform`, **never** `datasets.map`
- Audio is loaded **on-the-fly**, not precomputed
- Corrupt audio files are **skipped, not fatal**
- `dataloader_num_workers = 0` on Windows
- Training emits progress within 2 minutes
- Checkpoints are written incrementally
- Training is always resumable

If you violate any of these, training will fail.

---

## 6. Known Failure Modes (KFM)

These have all happened already.

### ❌ datasets.map over full dataset
- **Symptom:** `ArrowMemoryError`, realloc of 100GB+
- **Cause:** Arrow buffer explosion
- **Status:** FORBIDDEN

### ❌ batched=True for audio loading
- **Symptom:** `Invalid file: [list of paths]`
- **Cause:** `sf.read()` expects string, not list
- **Status:** FORBIDDEN

### ❌ num_workers > 0 on Windows
- **Symptom:** spawn / pickle / EOFError
- **Cause:** multiprocessing + closures
- **Status:** FORBIDDEN

### ❌ No try/except around sf.read
- **Symptom:** training stops at random sample
- **Status:** FORBIDDEN

---

## 7. Training Configuration (Golden Path)

This configuration is **known to be stable**.

```bash
python train_whisper.py \
  --model openai/whisper-medium \
  --train_jsonl build/splits/train.clean.nobom.jsonl \
  --val_jsonl build/splits/val.clean.nobom.jsonl \
  --out_dir build/models/whisper-medium/<runId> \
  --per_device_train_batch_size 2 \
  --gradient_accumulation_steps 4 \
  --num_workers 0 \
  --max_steps 20000
```

If this fails, something is fundamentally broken.

---

## 8. Expected Performance Envelope (RTX 4080)

| Phase | Expectation |
|-----|------------|
| First batch | 1–5 minutes |
| GPU memory | 6–10 GB |
| Throughput | ~1–2 steps/sec |
| Full run | ~4–6 hours |

GPU may appear idle briefly — this is normal.

---

## 9. Progress & Observability

### Logs (ALWAYS present)

```
logs/LATEST/
  trainer.log
  trainer.stderr.log
  audit.jsonl
  timings.jsonl
  errors.jsonl
```

### Signals you can trust
- tqdm step counter advancing
- GPU utilization > 0%
- Checkpoints appearing

### Signals you must IGNORE
- Deprecation warnings
- tqdm at 0% for <5 min
- GPU P8 state early on

---

## 10. Runbook — If Training Looks Stuck

1. Check stderr:

```powershell
Get-Content logs/LATEST/trainer.stderr.log -Tail 50
```

2. Check GPU:

```powershell
nvidia-smi
```

3. Check python:

```powershell
Get-Process python
```

### Interpretation
- ❌ No python + no GPU → crashed
- 🟡 Python alive, GPU idle <5 min → normal
- ✅ Python + GPU active → training OK

---

## 11. Recovery & Resume

- Checkpoints every N steps
- Safe to stop at any time
- Resume with:

```bash
--resume_from_checkpoint <checkpoint-path>
```

---

## 12. Explicit Non-Goals

- No Arrow/Parquet dataset materialization
- No multiprocessing audio loading on Windows
- No "perfect dataset" requirement
- No preprocessing speed optimizations at cost of stability

---

## 13. Architectural Rationale (WHY)

- Lazy loading avoids Arrow OOM
- Single-worker dataloader avoids Windows spawn bugs
- Skip-on-error maximizes usable data
- On-the-fly resampling avoids dataset duplication

---

## 14. Final Authority Rule

If:
- code
- scripts
- logs
- or human memory

conflict with **this document** → **THIS DOCUMENT IS CORRECT**.

---

**This contract exists to make the system boring, predictable, and resilient.**
