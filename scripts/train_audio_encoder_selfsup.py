import os
import json
import argparse
from datetime import datetime

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

from torchaudio.functional import resample as ta_resample
import soundfile as sf

def parse_args():
    p = argparse.ArgumentParser(description="Self-supervised Audio Encoder training for Norwegian Speech Base")
    p.add_argument("--data_index", type=str, required=True,
                   help="Path til norwegian_raw_wav_index.jsonl")
    p.add_argument("--output_dir", type=str, required=True,
                   help="Hvor modell og logger skal lagres")
    p.add_argument("--sample_rate", type=int, default=16000)
    p.add_argument("--clip_duration", type=float, default=2.0,
                   help="Kliplengde i sekunder for hver trenings-sample")
    p.add_argument("--batch_size", type=int, default=32)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()

class NorwegianRawAudioDataset(Dataset):
    def __init__(self, index_path, sample_rate=16000, clip_duration=2.0, split="train"):
        self.sample_rate = sample_rate
        self.clip_samples = int(sample_rate * clip_duration)
        self.items = []

        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                if obj.get("split", "train") == split:
                    wav_path = obj.get("original_path")
                    if wav_path and os.path.isfile(wav_path):
                        self.items.append(wav_path)

        if len(self.items) == 0:
            raise RuntimeError(f"Ingen wav-filer funnet for split='{split}' i {index_path}")

    def __len__(self):
        return len(self.items)

    def _load_audio(self, path):
        wav_np, sr = sf.read(path, always_2d=True)  # [T, C]
        wav_np = wav_np.T  # [C, T]
        wav = torch.from_numpy(wav_np).float()
        if wav.size(0) > 1:
            wav = wav.mean(dim=0, keepdim=True)
        if sr != self.sample_rate:
            wav = ta_resample(wav, orig_freq=sr, new_freq=self.sample_rate)
        return wav  # [1, T]

    def _random_crop(self, wav):
        T = wav.size(1)
        if T >= self.clip_samples:
            start = torch.randint(0, T - self.clip_samples + 1, (1,)).item()
            return wav[:, start:start+self.clip_samples]
        else:
            pad = self.clip_samples - T
            return F.pad(wav, (0, pad))

    def _augment(self, wav):
        wav = wav.clone()
        gain = 0.9 + 0.2 * torch.rand(1).item()
        wav = wav * gain
        noise_level = 0.01 * torch.rand(1).item()
        noise = noise_level * torch.randn_like(wav)
        wav = wav + noise
        return wav

    def __getitem__(self, idx):
        path = self.items[idx]
        wav = self._load_audio(path)
        wav = self._random_crop(wav)
        aug1 = self._augment(wav)
        aug2 = self._augment(wav)
        return aug1, aug2

class ConvEncoder(nn.Module):
    def __init__(self, in_channels=1, hidden_dim=256, proj_dim=128):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Conv1d(128, hidden_dim, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.proj = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, proj_dim),
        )

    def forward(self, x):
        h = self.conv(x)
        h = self.pool(h).squeeze(-1)
        z = self.proj(h)
        z = F.normalize(z, dim=-1)
        return h, z

def nt_xent_loss(z1, z2, temperature=0.1):
    batch_size = z1.size(0)
    z = torch.cat([z1, z2], dim=0)
    sim = torch.matmul(z, z.t())
    mask = torch.eye(2*batch_size, dtype=torch.bool, device=z.device)
    sim = sim.masked_fill(mask, -9e15)
    sim = sim / temperature
    targets = torch.arange(batch_size, 2*batch_size, device=z.device)
    targets = torch.cat([targets, torch.arange(0, batch_size, device=z.device)], dim=0)
    loss = F.cross_entropy(sim, targets)
    return loss

def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    device = torch.device(args.device)

    log_path = os.path.join(args.output_dir, "train_log.txt")
    print(f"[INFO] Starter trening. Logg: {log_path}", flush=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"=== Start {datetime.now().isoformat()} ===\n")
        lf.write(f"Args: {args}\n")

    dataset = NorwegianRawAudioDataset(
        index_path=args.data_index,
        sample_rate=args.sample_rate,
        clip_duration=args.clip_duration,
        split="train"
    )
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True,
                            num_workers=2, drop_last=True)

    model = ConvEncoder().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    total_steps = len(dataloader) * args.epochs
    global_step = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0

        for i, (aug1, aug2) in enumerate(dataloader, start=1):
            aug1 = aug1.to(device)
            aug2 = aug2.to(device)

            _, z1 = model(aug1)
            _, z2 = model(aug2)

            loss = nt_xent_loss(z1, z2, temperature=0.1)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            global_step += 1

            if i % 50 == 0 or i == len(dataloader):
                avg_loss = running_loss / i
                pct = 100.0 * (global_step / total_steps)
                msg = (f"[EPOCH {epoch}/{args.epochs}] "
                       f"step {i}/{len(dataloader)} "
                       f"({pct:.2f}% total) "
                       f"loss={avg_loss:.4f}")
                print(msg, flush=True)
                print(f"PROGRESS:{pct:.4f}", flush=True)
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(msg + "\n")

    final_path = os.path.join(args.output_dir, "audio_encoder_final.pt")
    torch.save(model.state_dict(), final_path)
    end_msg = f"[INFO] Ferdig trening. Lagret final model til {final_path}"
    print(end_msg, flush=True)
    print("PROGRESS:100.0", flush=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(end_msg + "\n")
        lf.write(f"=== Slutt {datetime.now().isoformat()} ===\n")

if __name__ == "__main__":
    main()
