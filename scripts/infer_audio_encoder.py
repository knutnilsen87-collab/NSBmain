import os, json, argparse
import numpy as np
import torch
import soundfile as sf
from torchaudio.functional import resample as ta_resample

from audio_encoder_model import Encoder

DEFAULT_SR = 16000
DEFAULT_PROJ = 128

def load_checkpoint(ckpt_path: str, device: str):
    d = torch.load(ckpt_path, map_location=device)
    # supports: {"model": state_dict, ...} OR raw state_dict
    if isinstance(d, dict) and "model" in d:
        state = d["model"]
        meta = d.get("meta", {})
    else:
        state = d
        meta = {}
    return state, meta

def load_wav(path: str, target_sr: int = DEFAULT_SR):
    wav_np, sr = sf.read(path, always_2d=True)
    wav_np = wav_np[:, 0] if wav_np.shape[1] > 0 else wav_np[:, 0]
    wav = torch.from_numpy(wav_np).float()
    if sr != target_sr:
        wav = ta_resample(wav, orig_freq=sr, new_freq=target_sr)
    if wav.numel() < 8:
        raise RuntimeError("Audio too short.")
    return wav, target_sr

def compute_embedding(model: Encoder, wav: torch.Tensor, sr: int, device: str, clip_sec: float = 2.0):
    # Use deterministic center crop/pad to fixed length for stable embeddings
    T = int(sr * clip_sec)
    if wav.numel() >= T:
        start = max(0, (wav.numel() - T) // 2)
        wav = wav[start:start + T]
    else:
        pad = T - wav.numel()
        wav = torch.nn.functional.pad(wav, (0, pad))
    x = wav.view(1, 1, -1).to(device)
    with torch.no_grad():
        emb = model(x).squeeze(0).detach().cpu().numpy()  # [proj]
    return emb

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True, help="Path to input wav")
    ap.add_argument("--checkpoint", required=False, default=None,
                    help="Checkpoint .pt. If omitted, tries models/audio_encoder/checkpoints/checkpoint_last.pt")
    ap.add_argument("--out_dir", required=False, default=None,
                    help="Output dir. Default: alongside wav.")
    ap.add_argument("--sample_rate", type=int, default=DEFAULT_SR)
    ap.add_argument("--proj_dim", type=int, default=DEFAULT_PROJ)
    ap.add_argument("--clip_sec", type=float, default=2.0)
    ap.add_argument("--device", default=("cuda" if torch.cuda.is_available() else "cpu"))
    args = ap.parse_args()

    wav_path = os.path.abspath(args.wav)
    if not os.path.isfile(wav_path):
        raise FileNotFoundError(wav_path)

    if args.checkpoint is None:
        # default to last checkpoint in project structure
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        args.checkpoint = os.path.join(project_root, "models", "audio_encoder", "checkpoints", "checkpoint_last.pt")

    ckpt = os.path.abspath(args.checkpoint)
    if not os.path.isfile(ckpt):
        raise FileNotFoundError(ckpt)

    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.dirname(wav_path)
    os.makedirs(out_dir, exist_ok=True)

    device = args.device
    model = Encoder(proj=args.proj_dim).to(device)
    state, meta = load_checkpoint(ckpt, device)
    model.load_state_dict(state)
    model.eval()

    wav, sr = load_wav(wav_path, target_sr=args.sample_rate)
    emb = compute_embedding(model, wav, sr, device=device, clip_sec=args.clip_sec)

    base = os.path.splitext(os.path.basename(wav_path))[0]
    npy_path = os.path.join(out_dir, f"{base}.embedding.npy")
    js_path  = os.path.join(out_dir, f"{base}.embedding.json")

    np.save(npy_path, emb)
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({
            "wav": wav_path,
            "checkpoint": ckpt,
            "proj_dim": int(args.proj_dim),
            "sample_rate": int(args.sample_rate),
            "clip_sec": float(args.clip_sec),
            "device": str(device),
            "embedding": emb.tolist(),
            "meta": meta
        }, f, ensure_ascii=False, indent=2)

    print(f"[OK] Saved: {npy_path}")
    print(f"[OK] Saved: {js_path}")

if __name__ == "__main__":
    main()
