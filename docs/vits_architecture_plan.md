# VITS Architecture Plan (NorwegianSpeechBase) — Using AudioEncoder_v2 as Speaker Conditioner

## Goal
Build a **Norwegian TTS MVP** with strong quality and a clean legal stance, using:
- **VITS** (end-to-end TTS)
- **AudioEncoder_v2 embeddings** as the speaker/voice conditioner

This yields:
- Multi-voice capability via embeddings (even if you start with 1–2 synthetic voices)
- A foundation path toward voice personalization later (with explicit consent voices)

---

## Baseline Decisions
**Recommended:** VITS first (quality + simplicity).
Avoid over-optimizing early.

### MVP Target
- Input: Norwegian text
- Output: WAV (22.05k or 24k is fine; 16k also ok for MVP)
- 1–2 voices (synthetic identity or legally safe voices)
- CLI first, then API

---

## Components

### 1) Text Front-End (Norwegian)
**Minimum viable:** character-level or phoneme-level.
**Recommended:** phonemes + stress markers once MVP works.

Pipeline:
- Normalize text (numbers, dates, abbreviations)
- Tokenize (chars/phonemes)
- Optional: prosody tags (later)

Deliverable:
- `text_normalizer_no.py`
- `tokenizer_no.py`

### 2) Speaker Conditioning (Your Encoder)
You already have:
- `infer_audio_encoder.py` → wav → embedding (dim=128 by default)

In VITS, inject speaker conditioning via:
- Add `speaker_embedding` into the encoder/decoder conditioning path
- Standard approach: a learned projection `Linear(emb_dim -> hidden_dim)` and add/concat to encoder hidden states
- Keep it simple: **concat** conditioning to text encoder outputs or **add** after projection

Deliverable:
- `speaker_conditioner.py` with:
  - `project(embedding) -> conditioning_vector`
  - caching for repeated inference (same voice)

### 3) VITS Acoustic Model
Core VITS blocks:
- Text Encoder
- Posterior Encoder
- Flow
- Generator (decoder)
- Multi-period discriminator(s)

Start with an existing well-known VITS reference implementation and modify:
- input tokens for Norwegian
- speaker conditioning input

Deliverable:
- `vits_no/` module
- config YAML

### 4) Vocoder
VITS contains a generator; no separate vocoder required.
(You can swap to BigVGAN later, but avoid now.)

---

## Data Requirements for TTS Stage
You need paired data:
- WAV + transcript

Options:
1) Use an existing Norwegian TTS dataset (license-safe) if available
2) Derive transcripts if the dataset includes them
3) Build a small consented studio dataset for 1–2 voices (fastest path to product quality)

**Important:** the raw audio used for the encoder is not automatically ready for TTS unless you have accurate text.

---

## Training Strategy (Pragmatic)
### Phase A — Single-voice VITS MVP
- train on one clean voice
- get good pronunciation and stability

### Phase B — Multi-voice conditioning
- add speaker conditioning with embeddings
- train with 2–5 voices
- verify voice separation and stability

### Phase C — Expressiveness
- prosody controls (rate, pitch, style)
- punctuation-aware phrasing
- optional emotion/style tokens

---

## Evaluation Checklist
- Pronunciation: numbers, dates, acronyms, names
- Long-form stability: 2–5 minute continuous generation
- Prosody: punctuation, questions, emphasis
- Speaker consistency: same embedding → consistent voice
- Speed: real-time factor (RTF)

---

## Milestone Roadmap
### Week 1
- Build text normalization/tokenizer
- Integrate speaker conditioner in VITS codebase
- Run first training on a small subset

### Week 2
- Improve stability (alignment, normalization, trimming)
- Produce a 60s demo audio from text

### Week 3
- Add 2nd voice
- Add caching + CLI tool

### Week 4
- Package into a local service (FastAPI or CLI-only)
- Prepare a clean “product demo” bundle

---

## Outputs & Packaging
Target:
- `tts_generate.py --text input.txt --voice ref.wav --out out.wav`
- Later:
  - `POST /tts {text, voice_id}`

---

## Non-Goals (for MVP)
- No voice cloning as a public product without explicit consent pipeline
- No UI before stable CLI/API
- No huge hyperparameter sweeps

---

## Next Actions (Developer Tasks)
1) Confirm embedding dim and stable inference using `compare_embeddings.py`
2) Choose tokenization: char vs phoneme
3) Pick a VITS reference implementation and add speaker conditioning projection
4) Identify a legally safe paired dataset for initial TTS training
5) Produce the first end-to-end demo
