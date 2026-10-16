"""Finjustering av Whisper/NB-Whisper på norsk, uten Arrow-cache.

Rettet oktober 2026 etter gjennomgang av kjøringene ALT2 og «True»:

1. Språk og oppgave settes (norsk, transcribe) både i etikettene og ved
   generering. Uten dette lærte modellen løkker og WER steg til ~9.
2. Strømmende stokking med fast frø. Før ble filen lest i rekkefølge, og bare
   de første ~22 % av NST ble sett.
3. Fasiter renses (``nsb_train_utils.clean_training_text``): stille opptak
   med tekst, usikre segmenter og uttalt tegnsetting (``\\Komma``).
4. Start-tokenet fjernes fra etikettene (Whisper legger det til selv).
5. Validering på et fast antall setninger med norsk normalisering, og beste
   modell lagres i ``best/`` etter WER. Bare de siste ``--keep_last``
   stegmappene beholdes.
6. Ugyldig ``--out_dir`` («True») stoppes.
"""

import argparse, json, os, sys, time, re, shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Dict, Any, Optional

import torch
from torch.utils.data import IterableDataset, DataLoader

import numpy as np
from tqdm import tqdm

from transformers import WhisperProcessor, WhisperForConditionalGeneration, get_linear_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nsb_train_utils import clean_training_text, shuffle_buffer, strip_decoder_start, validate_out_dir  # noqa: E402
from nsb_eval.metrics import EditCounts, word_counts  # noqa: E402
from nsb_eval.normalize import normalize  # noqa: E402

# -------------------- IO / safety
def utc_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def atomic_write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

def append_jsonl(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def log_state(out_dir: str, **fields):
    p = os.path.join(out_dir, "state.json")
    base = {}
    if os.path.exists(p):
        try:
            base = json.loads(open(p, "r", encoding="utf-8").read())
        except Exception:
            base = {}
    base.update({"ts_utc": utc_ts(), **fields})
    atomic_write(p, json.dumps(base, ensure_ascii=False, indent=2))

def count_jsonl_lines(path: str) -> int:
    # fast enough for ~hundreds of thousands of lines
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n

def latest_checkpoint_dir(ckpt_root: str) -> Optional[str]:
    if not os.path.isdir(ckpt_root):
        return None
    # step-<int>
    best = None
    best_step = -1
    for d in os.listdir(ckpt_root):
        m = re.match(r"step-(\d+)$", d)
        if not m:
            continue
        step = int(m.group(1))
        full = os.path.join(ckpt_root, d)
        if os.path.isdir(full) and step > best_step:
            best_step = step
            best = full
    return best

# -------------------- Audio
def _load_audio(path: str):
    try:
        import soundfile as sf
        wav, sr = sf.read(path)
        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)
        return wav.astype(np.float32), int(sr)
    except Exception:
        try:
            import torchaudio
            wav, sr = torchaudio.load(path)
            wav = wav.mean(dim=0).numpy().astype(np.float32)
            return wav, int(sr)
        except Exception as e:
            raise RuntimeError(f"Audio load failed for {path}: {e}")

def _resample_to_16k(wav: np.ndarray, sr: int) -> np.ndarray:
    if sr == 16000:
        return wav
    try:
        import torchaudio
        w = torch.from_numpy(wav).unsqueeze(0)
        w = torchaudio.functional.resample(w, orig_freq=sr, new_freq=16000)
        return w.squeeze(0).numpy().astype(np.float32)
    except Exception:
        import librosa
        return librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=16000).astype(np.float32)

# -------------------- Dataset
class JsonlAudioIterable(IterableDataset):
    """Leser JSONL linje for linje. Med ``shuffle_size > 1`` stokkes strømmen
    med et nytt, deterministisk frø for hver gjennomgang (epoke)."""

    def __init__(self, jsonl_path: str, processor: WhisperProcessor, max_rows: Optional[int] = None,
                 shuffle_size: int = 0, seed: int = 42, dictation: str = "symbol", stats: Optional[dict] = None):
        self.jsonl_path = jsonl_path
        self.processor = processor
        self.max_rows = max_rows
        self.shuffle_size = shuffle_size
        self.seed = seed
        self.dictation = dictation
        self.epoch = 0
        self.rows_consumed = 0  # rader lest fra strømmen i gjeldende epoke
        self.skip_rows = 0  # settes ved gjenopptaking
        self.stats = stats if stats is not None else {}

    def _iter_rows(self) -> Iterator[Dict[str, Any]]:
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if self.max_rows is not None and i >= self.max_rows:
                    break
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def _bump(self, key: str):
        self.stats[key] = self.stats.get(key, 0) + 1

    def __iter__(self):
        rows = self._iter_rows()
        if self.shuffle_size > 1:
            rows = shuffle_buffer(rows, self.shuffle_size, self.seed + self.epoch)
        self.epoch += 1
        skip, self.skip_rows = self.skip_rows, 0
        self.rows_consumed = 0
        for row in rows:
            self.rows_consumed += 1
            if self.rows_consumed <= skip:
                continue  # samme deterministiske rekkefølge som før avbruddet
            audio_path = row.get("audio") or row.get("path") or row.get("audio_path") or row.get("audio_filepath")
            raw_text = row.get("text") or row.get("transcript") or row.get("sentence")
            if not audio_path:
                self._bump("skip_no_audio")
                continue
            text, reason = clean_training_text(raw_text, dictation=self.dictation)
            if text is None:
                self._bump(f"skip_{reason}")
                continue

            try:
                wav, sr = _load_audio(audio_path)
            except RuntimeError:
                self._bump("skip_bad_audio")  # korrupte filer hoppes over (KFM i project.md)
                continue
            if sr != 16000:
                wav = _resample_to_16k(wav, sr)
                sr = 16000
            if len(wav) > 30 * 16000:
                self._bump("skip_longer_than_30s")
                continue

            inputs = self.processor.feature_extractor(wav, sampling_rate=sr, return_tensors="pt")
            # Tokenizeren har språk/oppgave som prefiks (set_prefix_tokens i main).
            label_ids = self.processor.tokenizer(text).input_ids
            if len(label_ids) > 448:  # Whispers maks dekoderlengde
                self._bump("skip_label_too_long")
                continue
            self._bump("used")

            yield {
                "input_features": inputs.input_features[0],
                "labels": torch.tensor(label_ids, dtype=torch.long),
            }

# -------------------- Collator
@dataclass
class Collator:
    processor: WhisperProcessor
    decoder_start_token_id: int

    def __call__(self, batch):
        for b in batch:
            b["labels"] = torch.tensor(
                strip_decoder_start(b["labels"].tolist(), self.decoder_start_token_id), dtype=torch.long
            )
        feats = [b["input_features"] for b in batch]
        max_len = max(x.shape[-1] for x in feats)
        feats_padded = []
        for x in feats:
            pad = max_len - x.shape[-1]
            if pad > 0:
                x = torch.nn.functional.pad(x, (0, pad))
            feats_padded.append(x)
        input_features = torch.stack(feats_padded, dim=0)

        # Fyll ut direkte med -100. Whisper har pad_token_id == eos_token_id, så
        # å maskere etter verdi (som før) fjernet også sluttokenet, og modellen
        # lærte aldri å stoppe.
        labels = [b["labels"] for b in batch]
        labels_padded = torch.nn.utils.rnn.pad_sequence(labels, batch_first=True, padding_value=-100)
        return {"input_features": input_features, "labels": labels_padded}

# -------------------- Checkpoint (crash-safe resume)
def save_ckpt(out_dir: str, step: int, model, processor, optim, sched, scaler, data_pos: Optional[dict] = None):
    """Skriver til step-N.tmp og døper om når alt er skrevet, slik at et
    avbrudd midt i lagringen aldri etterlater et halvt checkpoint."""
    final_dir = os.path.join(out_dir, "checkpoints", f"step-{step}")
    ckpt_dir = final_dir + ".tmp"
    shutil.rmtree(ckpt_dir, ignore_errors=True)
    os.makedirs(ckpt_dir, exist_ok=True)

    # Save HF artifacts
    model.save_pretrained(ckpt_dir)
    processor.save_pretrained(ckpt_dir)

    # Save training state
    state = {
        "step": step,
        "optimizer": optim.state_dict(),
        "scheduler": sched.state_dict(),
        "scaler": scaler.state_dict() if scaler is not None else None,
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        "numpy_rng": np.random.get_state(),
    }
    state["data_pos"] = data_pos or {}
    torch.save(state, os.path.join(ckpt_dir, "train_state.pt"))
    shutil.rmtree(final_dir, ignore_errors=True)
    os.replace(ckpt_dir, final_dir)

def load_ckpt(ckpt_dir: str, model, processor, optim, sched, scaler) -> tuple:
    # Load model/processor from same ckpt dir
    model2 = model.from_pretrained(ckpt_dir)
    model.load_state_dict(model2.state_dict())

    proc2 = processor.from_pretrained(ckpt_dir)
    processor.feature_extractor = proc2.feature_extractor
    processor.tokenizer = proc2.tokenizer

    st_path = os.path.join(ckpt_dir, "train_state.pt")
    if os.path.exists(st_path):
        # Egne checkpoints (inneholder numpy-RNG); torch >= 2.6 krever weights_only=False for dette.
        st = torch.load(st_path, map_location="cpu", weights_only=False)
        optim.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"])
        if scaler is not None and st.get("scaler") is not None:
            scaler.load_state_dict(st["scaler"])
        torch.set_rng_state(st["torch_rng"])
        if torch.cuda.is_available() and st.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(st["cuda_rng"])
        if st.get("numpy_rng") is not None:
            np.random.set_state(st["numpy_rng"])
        return int(st.get("step", 0)), st.get("data_pos") or {}
    raise RuntimeError(
        f"{st_path} mangler. Checkpointet er ufullstendig; slett {ckpt_dir} eller start uten --resume."
    )

# -------------------- Eval
def evaluate_wer(model, processor, val_loader, device, language: str) -> dict:
    """WER på hele valideringssettet med samme norske normalisering som
    nsb_eval, slik at tallene kan sammenlignes med målestokken."""
    model.eval()
    total = EditCounts()
    n = 0
    with torch.no_grad():
        for batch in val_loader:
            feats = batch["input_features"].to(device)
            labels = batch["labels"].detach().cpu().numpy()
            gen = model.generate(input_features=feats, language=language, task="transcribe", max_new_tokens=225)
            pred_str = processor.tokenizer.batch_decode(gen, skip_special_tokens=True)
            labels = np.where(labels == -100, processor.tokenizer.pad_token_id, labels)
            ref_str = processor.tokenizer.batch_decode(labels, skip_special_tokens=True)
            for ref, hyp in zip(ref_str, pred_str):
                total = total + word_counts(normalize(ref), normalize(hyp))
                n += 1
    model.train()
    return {"wer": total.error_rate if total.reference_length else None, "items": n, **total.to_dict()}


def rotate_checkpoints(ckpt_root: str, keep_last: int):
    steps = []
    for d in os.listdir(ckpt_root) if os.path.isdir(ckpt_root) else []:
        m = re.match(r"step-(\d+)$", d)
        if m:
            steps.append((int(m.group(1)), os.path.join(ckpt_root, d)))
    for _, path in sorted(steps)[:-keep_last] if keep_last > 0 else []:
        shutil.rmtree(path, ignore_errors=True)

# -------------------- Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_jsonl", required=True)
    ap.add_argument("--val_jsonl", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--model_name", default="NbAiLab/nb-whisper-medium",
                    help="Start fra NB-Whisper; openai/whisper-* virker også")
    ap.add_argument("--language", default="no", help="Whisper-språkkode: no (bokmål) eller nn (nynorsk)")
    ap.add_argument("--shuffle_size", type=int, default=5000, help="Bufferstørrelse for strømmende stokking")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dictation", choices=["symbol", "word"], default="symbol",
                    help="Uttalt tegnsetting i NST: symbol gir «,», word gir «komma»")
    ap.add_argument("--keep_last", type=int, default=2, help="Antall stegmapper som beholdes")
    ap.add_argument("--max_steps", type=int, default=20000)
    ap.add_argument("--eval_steps", type=int, default=200)
    ap.add_argument("--save_steps", type=int, default=200)
    ap.add_argument("--logging_steps", type=int, default=10)
    ap.add_argument("--batch_size", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--warmup_steps", type=int, default=500)
    ap.add_argument("--fp16", action="store_true")
    ap.add_argument("--pause_file", default=None)
    ap.add_argument("--limit_train", type=int, default=None)
    ap.add_argument("--limit_val", type=int, default=None)
    ap.add_argument("--resume", action="store_true", help="Auto-resume from latest checkpoint in out_dir")
    args = ap.parse_args()
    validate_out_dir(args.out_dir)
    if args.limit_val is None:
        args.limit_val = 500  # fast og stort nok valideringssett; tidligere bare 50 setninger

    os.makedirs(args.out_dir, exist_ok=True)
    log_state(args.out_dir, phase="INIT", sys_executable=sys.executable, argv=sys.argv)

    # Count total examples so we can show "remaining"
    train_total = count_jsonl_lines(args.train_jsonl)
    val_total = count_jsonl_lines(args.val_jsonl)
    if args.limit_train is not None:
        train_total = min(train_total, args.limit_train)
    if args.limit_val is not None:
        val_total = min(val_total, args.limit_val)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = WhisperProcessor.from_pretrained(args.model_name)
    processor.tokenizer.set_prefix_tokens(language=args.language, task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(args.model_name).to(device)
    model.generation_config.language = args.language
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None
    model.train()

    scaler = torch.cuda.amp.GradScaler(enabled=(args.fp16 and device == "cuda"))
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr)
    sched = get_linear_schedule_with_warmup(
        optim, num_warmup_steps=args.warmup_steps, num_training_steps=args.max_steps
    )

    data_stats = {}
    train_ds = JsonlAudioIterable(args.train_jsonl, processor, max_rows=args.limit_train,
                                  shuffle_size=args.shuffle_size, seed=args.seed, dictation=args.dictation,
                                  stats=data_stats)
    val_ds   = JsonlAudioIterable(args.val_jsonl, processor, max_rows=args.limit_val, dictation=args.dictation)
    collate  = Collator(processor, model.config.decoder_start_token_id)
    best_wer = None
    best_path = os.path.join(args.out_dir, "best_metrics.json")
    if os.path.exists(best_path):
        best_wer = json.loads(open(best_path, encoding="utf-8").read()).get("wer")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, num_workers=0, collate_fn=collate)
    val_loader   = DataLoader(val_ds, batch_size=args.batch_size, num_workers=0, collate_fn=collate)

    metrics_path = os.path.join(args.out_dir, "metrics.jsonl")

    # Resume
    start_step = 0
    ckpt_root = os.path.join(args.out_dir, "checkpoints")
    if args.resume:
        ckpt = latest_checkpoint_dir(ckpt_root)
        if ckpt:
            start_step, data_pos = load_ckpt(ckpt, model, processor, optim, sched, scaler)
            train_ds.epoch = int(data_pos.get("epoch", 0))
            train_ds.skip_rows = int(data_pos.get("rows_consumed", 0))
            processor.tokenizer.set_prefix_tokens(language=args.language, task="transcribe")
            log_state(args.out_dir, phase="RESUME", message=f"Resumed from {ckpt}", step=start_step)

    # Progress accounting: examples per epoch = train_total
    # We will show "epoch progress" as (examples_seen_in_epoch / train_total)
    examples_seen_in_epoch = (start_step * args.batch_size) % max(train_total, 1)

    log_state(args.out_dir, phase="TRAIN", max_steps=args.max_steps, )

    step = start_step
    it = iter(train_loader)

    # tqdm progressbar (steps)
    pbar = tqdm(total=args.max_steps, initial=step, dynamic_ncols=True)
    last_log = time.time()
    last_state_write = 0.0
    state_every_s = 5.0  # update state.json every N seconds for detached watcher

    while step < args.max_steps:
        # Pause support
        if args.pause_file and os.path.exists(args.pause_file):
            log_state(args.out_dir, phase="PAUSED", message="Pause file detected", step=step)
            time.sleep(2)
            continue

        try:
            batch = next(it)
        except StopIteration:
            it = iter(train_loader)
            batch = next(it)

        feats = batch["input_features"].to(device)
        labels = batch["labels"].to(device)

        with torch.cuda.amp.autocast(enabled=(args.fp16 and device == "cuda")):
            out = model(input_features=feats, labels=labels)
            loss = out.loss

        scaler.scale(loss).backward()
        scaler.step(optim)
        scaler.update()
        optim.zero_grad(set_to_none=True)
        sched.step()

        step += 1
        pbar.update(1)

        # Update "examples remaining" estimate within current epoch
        examples_seen_in_epoch = (examples_seen_in_epoch + args.batch_size) % max(train_total, 1)
        remaining = (train_total - examples_seen_in_epoch) if train_total > 0 else 0

        # Update tqdm postfix (ETA comes from tqdm)
        pbar.set_postfix({
            "loss": f"{float(loss.detach().cpu().item()):.4f}",
            "seen": f"{examples_seen_in_epoch}/{train_total}",
            "remain": remaining
        })

        now = time.time()
        if now - last_state_write >= state_every_s:
            # "files remaining" in current epoch (approx, since streaming order is linear)
            remain_in_epoch = (train_total - examples_seen_in_epoch) if train_total > 0 else 0
            global_examples_seen = step * args.batch_size
            log_state(
                args.out_dir,
                phase="TRAIN",
                step=step,
                max_steps=args.max_steps,
                train_total=train_total,
                examples_seen_in_epoch=int(examples_seen_in_epoch),
                remain_in_epoch=int(remain_in_epoch),
                global_examples_seen=int(global_examples_seen),
                batch_size=args.batch_size,
            )
            last_state_write = now
        # Structured metrics (crash-safe append)
        if step % args.logging_steps == 0:
            append_jsonl(metrics_path, {"ts_utc": utc_ts(), "step": step, "loss": float(loss.detach().cpu().item())})

        # Periodic eval
        if step % args.eval_steps == 0:
            ev = evaluate_wer(model, processor, val_loader, device, args.language)
            append_jsonl(metrics_path, {"ts_utc": utc_ts(), "step": step, **ev, "data": dict(data_stats)})
            if ev["wer"] is not None and (best_wer is None or ev["wer"] < best_wer):
                best_wer = ev["wer"]
                best_dir = os.path.join(args.out_dir, "best")
                model.save_pretrained(best_dir)
                processor.save_pretrained(best_dir)
                atomic_write(best_path, json.dumps({"step": step, **ev}, ensure_ascii=False, indent=2))
            log_state(args.out_dir, phase="TRAIN", max_steps=args.max_steps, best_wer=best_wer)

        # Periodic checkpoint (power-loss safe)
        if step % args.save_steps == 0:
            save_ckpt(args.out_dir, step, model, processor, optim, sched, scaler,
                      data_pos={"epoch": max(train_ds.epoch - 1, 0), "rows_consumed": train_ds.rows_consumed})
            rotate_checkpoints(ckpt_root, args.keep_last)
            log_state(args.out_dir, phase="TRAIN", max_steps=args.max_steps, )

    pbar.close()
    log_state(args.out_dir, phase="DONE", message="Training finished", step=step)

if __name__ == "__main__":
    main()


