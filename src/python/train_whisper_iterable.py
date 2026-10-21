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

def replace_with_retry(src: str, dst: str, tries: int = 20, wait: float = 0.5):
    """``os.replace`` som tåler at Windows holder fila et øyeblikk.

    Antivirus, søkeindeksering og synkronisering (OneDrive, Google Drive) kan
    låse en fil i noen sekunder; da gir ``os.replace`` «[WinError 5] Ingen
    tilgang». Et slikt kortvarig hinder skal ikke stoppe en treningskjøring.
    """
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(wait * (1 + i))


def atomic_write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    replace_with_retry(tmp, path)

def append_jsonl(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def log_state(out_dir: str, **fields):
    p = os.path.join(out_dir, "state.json")
    base = {}
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                base = json.loads(f.read())
        except Exception:
            base = {}
    base.update({"ts_utc": utc_ts(), **fields})
    try:
        atomic_write(p, json.dumps(base, ensure_ascii=False, indent=2))
    except PermissionError as e:
        # state.json er bare en statuslogg; treningen fortsetter uten den.
        print(f"[advarsel] kunne ikke skrive {p}: {e}", flush=True)

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
                 shuffle_size: int = 0, seed: int = 42, dictation: str = "symbol", stats: Optional[dict] = None,
                 default_language: str = "no", only_language: Optional[str] = None):
        self.default_language = default_language
        self.only_language = only_language  # brukes for validering per språk
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
            if self.only_language and (row.get("language") or self.default_language) != self.only_language:
                continue
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
            # Språktoken per rad (``language``: no/nn) hvis manifestet har det,
            # ellers språket satt i main. Nynorsk trenes da med <|nn|>.
            language = row.get("language") or self.default_language
            label_ids = labels_for(self.processor.tokenizer, text, language)
            if len(label_ids) > 448:  # Whispers maks dekoderlengde
                self._bump("skip_label_too_long")
                continue
            self._bump("used")

            yield {
                "input_features": inputs.input_features[0],
                "labels": torch.tensor(label_ids, dtype=torch.long),
            }

def labels_for(tokenizer, text: str, language: str) -> list:
    """Etikett med <|startoftranscript|><|språk|><|transcribe|><|notimestamps|> først
    og <|endoftext|> sist. Prefikset settes per kall, siden språket kan variere."""
    if getattr(tokenizer, "language", None) != language:
        tokenizer.set_prefix_tokens(language=language, task="transcribe")
    return tokenizer(text).input_ids


def freeze_encoder(model, layers: int) -> int:
    """Fryser konvolusjonene, posisjonene og de nederste ``layers`` lagene i
    koderen. Gir færre parametre å trene (og plass til en stor koder på 16 GB),
    mens de øverste lagene og dekoderen lærer dialekt og skrivemåte.
    Returnerer antall trenbare parametre."""
    enc = model.model.encoder
    if layers > 0:
        for module in (enc.conv1, enc.conv2, enc.embed_positions):
            for p in module.parameters():
                p.requires_grad = False
        for layer in enc.layers[:layers]:
            for p in layer.parameters():
                p.requires_grad = False
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


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

    # Save HF artifacts (i biter på 1 GB: mindre minne under lagring)
    model.save_pretrained(ckpt_dir, max_shard_size=SHARD)
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
    replace_with_retry(ckpt_dir, final_dir)

SHARD = "1GB"


def save_best(out_dir: str, model, processor) -> bool:
    """Lagrer beste modell i ``best/`` uten å skrive over den gamle før den nye er ferdig.

    Den nye modellen skrives til ``best.tmp`` og byttes inn med navnebytter.
    Feiler lagringen, beholdes forrige ``best/`` og treningen fortsetter.
    """
    best, tmp, old = (os.path.join(out_dir, n) for n in ("best", "best.tmp", "best.old"))
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        model.save_pretrained(tmp, max_shard_size=SHARD)
        processor.save_pretrained(tmp)
        shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(best):
            replace_with_retry(best, old)
        replace_with_retry(tmp, best)
        shutil.rmtree(old, ignore_errors=True)
        return True
    except Exception as e:  # noqa: BLE001 - en mislykket lagring skal ikke stoppe treningen
        print(f"[advarsel] kunne ikke lagre beste modell: {type(e).__name__}: {e}", flush=True)
        if not os.path.isdir(best) and os.path.isdir(old):
            os.replace(old, best)
        return False


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
    dtype = next(p for p in model.parameters()).dtype
    with torch.no_grad():
        for batch in val_loader:
            feats = batch["input_features"].to(device, dtype=dtype)
            labels = batch["labels"].detach().cpu().numpy()
            gen = model.generate(input_features=feats, language=language, task="transcribe", max_new_tokens=225,
                                 use_cache=True)
            pred_str = processor.tokenizer.batch_decode(gen, skip_special_tokens=True)
            labels = np.where(labels == -100, processor.tokenizer.pad_token_id, labels)
            ref_str = processor.tokenizer.batch_decode(labels, skip_special_tokens=True)
            for ref, hyp in zip(ref_str, pred_str):
                total = total + word_counts(normalize(ref), normalize(hyp))
                n += 1
    model.train()
    return {"wer": total.error_rate if total.reference_length else None, "items": n, **total.to_dict()}


def evaluate_languages(model, processor, loaders: dict, device) -> dict:
    """WER per språk og samlet (ordvektet), for valg av beste checkpoint."""
    per = {lang: evaluate_wer(model, processor, loader, device, lang) for lang, loader in loaders.items()}
    errors = sum(v["errors"] for v in per.values() if v["items"])
    ref = sum(v["reference_length"] for v in per.values() if v["items"])
    out = {"wer": errors / ref if ref else None, "items": sum(v["items"] for v in per.values())}
    for lang, v in per.items():
        out[f"wer_{lang}"] = v["wer"]
        out[f"items_{lang}"] = v["items"]
    return out


def rotate_checkpoints(ckpt_root: str, keep_last: int):
    for d in os.listdir(ckpt_root) if os.path.isdir(ckpt_root) else []:
        if d.endswith(".tmp"):  # rester etter avbrutt lagring
            shutil.rmtree(os.path.join(ckpt_root, d), ignore_errors=True)
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
    ap.add_argument("--bf16", action="store_true", help="bfloat16 autocast (RTX 30/40), uten GradScaler")
    ap.add_argument("--eval_at_start", action="store_true",
                    help="Valider før første steg (steg 0), så utgangsmodellen er sammenligningsgrunnlaget")
    ap.add_argument("--grad_accum", type=int, default=1, help="Akkumuler gradienter over så mange batcher")
    ap.add_argument("--freeze_encoder_layers", type=int, default=0, help="Frys de nederste N lagene i koderen")
    ap.add_argument("--gradient_checkpointing", action="store_true")
    ap.add_argument("--spec_augment", action="store_true", help="SpecAugment (maskering i tid og frekvens) under trening")
    ap.add_argument("--val_languages", default=None,
                    help="Kommaseparerte språk (for eksempel no,nn): validering per språk med riktig språktoken")
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
    model = WhisperForConditionalGeneration.from_pretrained(args.model_name)
    if args.spec_augment:
        model.config.apply_spec_augment = True
        model.config.mask_time_prob = 0.05
        model.config.mask_feature_prob = 0.05
    trainable = freeze_encoder(model, args.freeze_encoder_layers)
    if args.gradient_checkpointing:
        model.config.use_cache = False
        model.gradient_checkpointing_enable()
    model = model.to(device)
    log_state(args.out_dir, phase="INIT", trainable_parameters=int(trainable),
              total_parameters=int(sum(p.numel() for p in model.parameters())))
    model.generation_config.language = args.language
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None
    model.train()

    use_fp16 = args.fp16 and not args.bf16 and device == "cuda"
    amp_dtype = torch.bfloat16 if args.bf16 else torch.float16
    use_amp = device == "cuda" and (args.fp16 or args.bf16)
    scaler = torch.cuda.amp.GradScaler(enabled=use_fp16)
    optim = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr)
    sched = get_linear_schedule_with_warmup(
        optim, num_warmup_steps=args.warmup_steps, num_training_steps=args.max_steps
    )

    data_stats = {}
    train_ds = JsonlAudioIterable(args.train_jsonl, processor, max_rows=args.limit_train,
                                  shuffle_size=args.shuffle_size, seed=args.seed, dictation=args.dictation,
                                  stats=data_stats, default_language=args.language)
    val_languages = [x.strip() for x in args.val_languages.split(",")] if args.val_languages else [args.language]
    collate  = Collator(processor, model.config.decoder_start_token_id)
    best_wer = None
    best_path = os.path.join(args.out_dir, "best_metrics.json")
    if os.path.exists(best_path):
        best_wer = json.loads(open(best_path, encoding="utf-8").read()).get("wer")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, num_workers=0, collate_fn=collate)
    val_loaders = {
        lang: DataLoader(
            JsonlAudioIterable(args.val_jsonl, processor, max_rows=args.limit_val, dictation=args.dictation,
                               default_language=args.language, only_language=lang if args.val_languages else None),
            batch_size=args.batch_size, num_workers=0, collate_fn=collate)
        for lang in val_languages
    }

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
    if args.eval_at_start and step == 0 and best_wer is None:
        ev = evaluate_languages(model, processor, val_loaders, device)
        processor.tokenizer.set_prefix_tokens(language=args.language, task="transcribe")
        append_jsonl(metrics_path, {"ts_utc": utc_ts(), "step": 0, **ev, "baseline": True})
        atomic_write(os.path.join(args.out_dir, "baseline_metrics.json"), json.dumps({"step": 0, **ev}, ensure_ascii=False, indent=2))
        log_state(args.out_dir, phase="TRAIN", baseline_wer=ev["wer"])

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

        for _ in range(args.grad_accum):
            try:
                batch = next(it)
            except StopIteration:
                it = iter(train_loader)
                batch = next(it)

            feats = batch["input_features"].to(device)
            labels = batch["labels"].to(device)

            with torch.autocast(device_type="cuda", dtype=amp_dtype, enabled=use_amp):
                out = model(input_features=feats, labels=labels)
                loss = out.loss / args.grad_accum

            scaler.scale(loss).backward()
        scaler.step(optim)
        scaler.update()
        optim.zero_grad(set_to_none=True)
        sched.step()

        step += 1
        pbar.update(1)

        # Update "examples remaining" estimate within current epoch
        examples_seen_in_epoch = (examples_seen_in_epoch + args.batch_size * args.grad_accum) % max(train_total, 1)
        remaining = (train_total - examples_seen_in_epoch) if train_total > 0 else 0

        # Update tqdm postfix (ETA comes from tqdm)
        pbar.set_postfix({
            "loss": f"{float(loss.detach().cpu().item()) * args.grad_accum:.4f}",
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
            append_jsonl(metrics_path, {"ts_utc": utc_ts(), "step": step, "loss": float(loss.detach().cpu().item()) * args.grad_accum})

        # Periodic eval
        if step % args.eval_steps == 0:
            ev = evaluate_languages(model, processor, val_loaders, device)
            processor.tokenizer.set_prefix_tokens(language=args.language, task="transcribe")
            append_jsonl(metrics_path, {"ts_utc": utc_ts(), "step": step, **ev, "data": dict(data_stats)})
            if ev["wer"] is not None and (best_wer is None or ev["wer"] < best_wer):
                if save_best(args.out_dir, model, processor):
                    best_wer = ev["wer"]
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


