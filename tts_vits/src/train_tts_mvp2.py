import argparse, time
from pathlib import Path
import torch
import torch.nn as nn
import torchaudio
from torch.utils.data import Dataset, DataLoader

def now(): return time.time()
def eta_min_hours(sec: float):
    m = max(0.0, sec/60.0)
    h = max(0.0, m/60.0)
    return m, h

class MetaDataset(Dataset):
    def __init__(self, dataset_root: Path, metadata_csv: Path, sample_rate=22050, n_mels=80, max_text_len=256):
        self.dataset_root = dataset_root
        self.wavs_dir = dataset_root / "wavs"
        self.sample_rate = sample_rate
        self.max_text_len = max_text_len

        lines = metadata_csv.read_text(encoding="utf-8", errors="ignore").splitlines()
        self.items = []
        for ln in lines:
            ln = ln.strip()
            if not ln or ln.startswith("#"): continue
            if "|" not in ln: continue
            utt, text = ln.split("|", 1)
            utt = utt.strip(); text = text.strip()
            if not utt or not text: continue
            wav = self.wavs_dir / f"{utt}.wav"
            if wav.exists():
                self.items.append((wav, text))

        if len(self.items) == 0:
            raise RuntimeError("0 usable items found: metadata did not match wavs/utt_*.wav naming")

        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=sample_rate, n_fft=1024, hop_length=256, win_length=1024, n_mels=n_mels
        )
        self.amp_to_db = torchaudio.transforms.AmplitudeToDB(stype="power")

        base = list("abcdefghijklmnopqrstuvwxyzæøåABCDEFGHIJKLMNOPQRSTUVWXYZÆØÅ0123456789 .,;:!?\"'()-")
        self.stoi = {"<pad>": 0, "<unk>": 1}
        for ch in base:
            if ch not in self.stoi:
                self.stoi[ch] = len(self.stoi)

    def __len__(self): return len(self.items)

    def encode_text(self, text: str):
        text = text[: self.max_text_len]
        ids = [self.stoi.get(ch, 1) for ch in text]
        return torch.tensor(ids, dtype=torch.long)

    def __getitem__(self, idx):
        wav_path, text = self.items[idx]
        wav, sr = torchaudio.load(str(wav_path))
        if wav.size(0) > 1: wav = wav.mean(dim=0, keepdim=True)
        if sr != self.sample_rate:
            wav = torchaudio.functional.resample(wav, sr, self.sample_rate)
        m = self.amp_to_db(self.mel(wav)).squeeze(0)  # [n_mels, T]
        target = m.mean(dim=1)                        # [n_mels]
        tokens = self.encode_text(text)
        return tokens, target

def collate(batch):
    tokens, targets = zip(*batch)
    maxlen = max(t.size(0) for t in tokens)
    padded = torch.zeros(len(tokens), maxlen, dtype=torch.long)
    mask = torch.zeros(len(tokens), maxlen, dtype=torch.float32)
    for i,t in enumerate(tokens):
        padded[i, :t.size(0)] = t
        mask[i, :t.size(0)] = 1.0
    targets = torch.stack(targets, dim=0)
    return padded, mask, targets

class TextToMelMean(nn.Module):
    def __init__(self, vocab_size: int, n_mels=80, hidden=256):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, hidden)
        self.proj = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, n_mels))
    def forward(self, tokens, mask):
        x = self.emb(tokens)
        denom = mask.sum(dim=1, keepdim=True).clamp(min=1.0)
        pooled = (x * mask.unsqueeze(-1)).sum(dim=1) / denom
        return self.proj(pooled)

def save_ckpt(path: Path, model, optim, epoch, step):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(),"optim": optim.state_dict(),"epoch": epoch,"step": step}, str(path))

def try_resume(ckpt_last: Path, model, optim):
    if not ckpt_last.exists(): return 1, 0
    ckpt = torch.load(str(ckpt_last), map_location="cpu")
    model.load_state_dict(ckpt["model"])
    optim.load_state_dict(ckpt["optim"])
    epoch = int(ckpt.get("epoch", 1))
    step  = int(ckpt.get("step", 0))
    print(f"[RESUME] ckpt_last={ckpt_last} epoch={epoch} step={step}", flush=True)
    return epoch, step

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_root", required=True)
    ap.add_argument("--metadata_csv", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch_size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--num_workers", type=int, default=0)
    ap.add_argument("--save_every", type=int, default=500)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    ckpt_dir = out_dir / "checkpoints"
    ckpt_last = ckpt_dir / "checkpoint_last.pt"

    ds = MetaDataset(Path(args.dataset_root), Path(args.metadata_csv))
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, collate_fn=collate)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TextToMelMean(vocab_size=len(ds.stoi)).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    start_epoch = 1
    step = 0
    if args.resume:
        start_epoch, step = try_resume(ckpt_last, model, optim)

    total_steps = args.epochs * len(dl)
    t0 = now()

    print(f"[INFO] device={device} items={len(ds)} batches/epoch={len(dl)} total_steps={total_steps}", flush=True)
    print("PROGRESS:0.00", flush=True)

    # If resuming, we still compute pct against total_steps
    for epoch in range(start_epoch, args.epochs + 1):
        for bi, (tokens, mask, target) in enumerate(dl, start=1):
            step += 1
            tokens = tokens.to(device); mask = mask.to(device); target = target.to(device)

            pred = model(tokens, mask)
            loss = loss_fn(pred, target)

            optim.zero_grad(set_to_none=True)
            loss.backward()
            optim.step()

            pct = (step / max(1, total_steps)) * 100.0
            dt = now() - t0
            spd = dt / max(1, step)
            eta_sec = spd * max(0, (total_steps - step))
            m, h = eta_min_hours(eta_sec)

            if step % 10 == 0 or step == 1:
                print(f"[EPOCH {epoch}/{args.epochs}] step {bi}/{len(dl)} ({pct:.2f}% total) loss={loss.item():.4f} ETA_MIN={m:.1f} ETA_H={h:.2f}", flush=True)
                print(f"PROGRESS:{pct:.2f}", flush=True)

            if step % args.save_every == 0:
                save_ckpt(ckpt_dir / f"checkpoint_step_{step:07d}.pt", model, optim, epoch, step)
                save_ckpt(ckpt_last, model, optim, epoch, step)
                print(f"[CKPT] saved step={step} -> {ckpt_last}", flush=True)

        save_ckpt(ckpt_dir / f"checkpoint_epoch_{epoch:03d}.pt", model, optim, epoch, step)
        save_ckpt(ckpt_last, model, optim, epoch, step)
        print(f"[CKPT] epoch_end saved -> {ckpt_last}", flush=True)

    print("PROGRESS:100.00", flush=True)
    print(f"[OK] Training done. ckpt_last={ckpt_last}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
