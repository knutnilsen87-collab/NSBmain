import os, sys
from pathlib import Path
# Ensure project root (tts_vits) is on sys.path so "import src.*" works reliably
_THIS = Path(__file__).resolve()
_TTS_ROOT = _THIS.parent.parent  # .../tts_vits
if str(_TTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TTS_ROOT))
import os, time, argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import soundfile as sf

# --- FBL_ENV_PULSE_PATCH START ---
import os
import time

def _fbl_env_int(name: str, default: int) -> int:
    try:
        v = os.environ.get(name, "")
        if v is None or v == "":
            return int(default)
        return int(v)
    except Exception:
        return int(default)

def _fbl_ckpt_dir(out_dir: str) -> str:
    d = os.path.join(out_dir, "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d

def _fbl_stop_path(out_dir: str) -> str:
    return os.path.join(out_dir, "STOP")

def _fbl_save_ckpt(out_dir: str, tag: str, **payload):
    ckpt_dir = _fbl_ckpt_dir(out_dir)
    path = os.path.join(ckpt_dir, f"{tag}.pt")
    try:
        import torch
        torch.save(payload, path)
        print(f"FBL_CKPT_SAVED path={path}", flush=True)
        return True
    except Exception as e:
        print(f"FBL_CKPT_SAVE_FAILED err={e}", flush=True)
        return False
# --- FBL_ENV_PULSE_PATCH END ---
# --- FBL_PULSE_SAVE_PATCH START ---
import os
import time

def _fbl_ckpt_dir(out_dir: str) -> str:
    d = os.path.join(out_dir, "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d

def _fbl_stop_path(out_dir: str) -> str:
    return os.path.join(out_dir, "STOP")

def _fbl_try_save(out_dir: str, tag: str, **kw):
    """
    Best-effort checkpoint saver.
    Tries common VITS variable names if present in locals/globals.
    """
    ckpt_dir = _fbl_ckpt_dir(out_dir)
    path = os.path.join(ckpt_dir, f"{tag}.pt")

    payload = {
        "tag": tag,
        "time": time.time(),
    }

    # accept explicit items if passed
    for k, v in kw.items():
        payload[k] = v

    # Try common names in scope (won't crash if absent)
    scope = {}
    try:
        scope.update(globals())
    except Exception:
        pass
    try:
        scope.update(locals())
    except Exception:
        pass

    def put(name, key):
        if name in scope and scope[name] is not None:
            try:
                obj = scope[name]
                # torch modules/optimizers
                if hasattr(obj, "state_dict"):
                    payload[key] = obj.state_dict()
                else:
                    payload[key] = obj
            except Exception:
                pass

    put("net_g", "net_g")
    put("net_d", "net_d")
    put("optim_g", "optim_g")
    put("optim_d", "optim_d")
    put("optimizer", "optimizer")
    put("model", "model")

    # metadata (common)
    for k in ("epoch", "epochs", "global_step", "step", "out_dir"):
        if k in scope:
            try: payload[k] = int(scope[k]) if str(scope[k]).isdigit() else scope[k]
            except Exception: payload[k] = scope[k]

    try:
        import torch
        torch.save(payload, path)
        print(f"FBL_CKPT_SAVED path={path}", flush=True)
    except Exception as e:
        print(f"FBL_CKPT_SAVE_FAILED err={e}", flush=True)

def _fbl_maybe_add_args(parser):
    # Adds new args without breaking existing CLI
    try:
        parser.add_argument("--save_every", type=int, default=500, help="Save checkpoint every N steps (FBL patch).")
        parser.add_argument("--pulse_steps", type=int, default=0, help="Exit cleanly after N steps (FBL patch). 0=disabled.")
    except Exception:
        pass
    return parser

# --- FBL_PULSE_SAVE_PATCH END ---
# --- FBL PATCH START (wav resolve + progress) ---
import os
import time

def resolve_wav_path(path: str) -> str:
    if not isinstance(path, str):
        path = str(path)
    base, ext = os.path.splitext(path)
    tried = []
    if ext:
        tried.append(path)
        if os.path.exists(path):
            return path
    else:
        for e in (".wav", ".WAV"):
            p = path + e
            tried.append(p)
            if os.path.exists(p):
                return p
        tried.append(path)
    raise FileNotFoundError(
        "WAV not found. Tried: " + " | ".join(tried) +
        "  (Hint: metadata id may miss .wav, or wavs path mismatch.)"
    )

class _FBLRate:
    def __init__(self):
        self.last_t = time.time()
        self.ema_s = None
    def step(self, k=1):
        now = time.time()
        dt = max(1e-6, now - self.last_t)
        self.last_t = now
        sps = dt / max(1, k)
        if self.ema_s is None:
            self.ema_s = sps
        else:
            self.ema_s = (0.95 * self.ema_s) + (0.05 * sps)
        return self.ema_s
# --- FBL PATCH END ---
from src.text_normalizer_no import normalize_no
from src.tokenizer_no import CharTokenizer
from src.vits_model import VITS

def read_metadata(metadata_csv: str):
    items = []
    with open(metadata_csv, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            wav, text = line.split("|", 1)
            items.append((wav.strip(), text.strip()))
    if not items:
        raise RuntimeError("metadata.csv has no usable lines.")
    return items

class TTSDataset(torch.utils.data.Dataset):
    def __init__(self, root: str, metadata_csv: str, sample_rate: int = 22050, max_seconds: float = 12.0):
        self.root = root
        self.wavs_dir = os.path.join(root, "wavs")
        self.items = read_metadata(metadata_csv)
        self.sr = sample_rate
        self.max_T = int(sample_rate * max_seconds)
        self.tokenizer = CharTokenizer()

        # Build vocab upfront for stable embedding size
        for _, text in self.items:
            t = normalize_no(text)
            _ = self.tokenizer.encode(t)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        fn, text = self.items[idx]
        wav_path = os.path.join(self.wavs_dir, fn)
        wav, sr = sf.read(resolve_wav_path(wav_path), always_2d=True)
        wav = wav[:, 0].astype(np.float32)

        if sr != self.sr:
            raise RuntimeError(f"Sample rate mismatch for {wav_path}: {sr} != {self.sr}")

        # Trim/pad for MVP stability
        if wav.shape[0] > self.max_T:
            start = max(0, (wav.shape[0] - self.max_T)//2)
            wav = wav[start:start+self.max_T]
        else:
            pad = self.max_T - wav.shape[0]
            wav = np.pad(wav, (0, pad))

        text = normalize_no(text)
        ids = self.tokenizer.encode(text)

        return torch.tensor(ids, dtype=torch.long), torch.tensor(wav, dtype=torch.float32)

def collate(batch):
    token_seqs, wavs = zip(*batch)
    max_len = max([t.numel() for t in token_seqs])
    tokens = torch.zeros((len(batch), max_len), dtype=torch.long)
    lengths = torch.tensor([t.numel() for t in token_seqs], dtype=torch.long)
    for i, t in enumerate(token_seqs):
        tokens[i, :t.numel()] = t
    wavs = torch.stack([w for w in wavs], dim=0)
    return tokens, lengths, wavs

def save_ckpt(path, model, opt, step, epoch):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save({
        "model": model.state_dict(),
        "opt": opt.state_dict(),
        "step": step,
        "epoch": epoch
    }, path)

def load_ckpt(path, model, opt):
    d = torch.load(path, map_location="cpu")
    model.load_state_dict(d["model"])
    opt.load_state_dict(d["opt"])
    return int(d.get("step", 0)), int(d.get("epoch", 0))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_root", required=True)
    ap.add_argument("--metadata_csv", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--sample_rate", type=int, default=22050)
    ap.add_argument("--batch_size", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--num_workers", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--device", default=("cuda" if torch.cuda.is_available() else "cpu"))
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    ckpt_dir = os.path.join(args.out_dir, "checkpoints")
    log_path = os.path.join(args.out_dir, "train_log.txt")
    last_ckpt = os.path.join(ckpt_dir, "checkpoint_last.pt")

    def log(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    ds = TTSDataset(args.dataset_root, args.metadata_csv, sample_rate=args.sample_rate)
    dl = torch.utils.data.DataLoader(ds, batch_size=args.batch_size, shuffle=True,
                                     num_workers=args.num_workers, collate_fn=collate, drop_last=True)

    vocab_size = len(ds.tokenizer.stoi)
    model = VITS(vocab_size=vocab_size, hidden_dim=192, speaker_emb_dim=128).to(args.device)
    opt = optim.AdamW(model.parameters(), lr=args.lr)
    crit = nn.MSELoss()

    step = 0
    start_epoch = 0
    if args.resume and os.path.isfile(last_ckpt):
        step, start_epoch = load_ckpt(last_ckpt, model, opt)
        log(f"Resumed from {last_ckpt} at epoch={start_epoch} step={step}")
    else:
        log("Starting fresh training run.")

    total_steps = args.epochs * len(dl)
    t0 = time.time()
    ema_sps = None

    for epoch in range(start_epoch, args.epochs):
        model.train()
        for b, (tokens, lengths, wavs) in enumerate(dl, start=1):
            step += 1
            tokens = tokens.to(args.device)
            # Single-speaker MVP: constant spk embedding
            spk = torch.zeros((tokens.shape[0], 128), device=args.device)

            out = model(tokens, spk)
            target = torch.zeros_like(out)
            loss = crit(out, target)

            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()

            elapsed = time.time() - t0
            sps = step / max(elapsed, 1e-6)
            ema_sps = sps if ema_sps is None else (0.9*ema_sps + 0.1*sps)
            remaining = max(total_steps - step, 0)
            eta_sec = remaining / max(ema_sps, 1e-6)

            if step % 10 == 0:
                pct = (step / total_steps) * 100.0
                log(f"[EPOCH {epoch+1}/{args.epochs}] step {b}/{len(dl)} ({pct:.2f}% total) loss={loss.item():.4f} ETA={eta_sec/60:.1f} min")

            if step % 200 == 0:
                save_ckpt(last_ckpt, model, opt, step, epoch)
                log(f"Saved checkpoint_last.pt at step={step}")

        save_ckpt(last_ckpt, model, opt, step, epoch+1)
        log(f"Epoch done. Saved checkpoint_last.pt (epoch={epoch+1})")

    log("TRAINING COMPLETE.")

if __name__ == "__main__":
    main()













