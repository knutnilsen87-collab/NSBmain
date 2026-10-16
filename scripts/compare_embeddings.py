import os, argparse
import numpy as np
import torch
import soundfile as sf
from torchaudio.functional import resample as ta_resample

from audio_encoder_model import Encoder
from infer_audio_encoder import load_checkpoint, compute_embedding

DEFAULT_SR=16000
DEFAULT_PROJ=128

def load_wav(path: str, target_sr: int = DEFAULT_SR):
    wav_np, sr = sf.read(path, always_2d=True)
    wav_np = wav_np[:, 0] if wav_np.shape[1] > 0 else wav_np[:, 0]
    wav = torch.from_numpy(wav_np).float()
    if sr != target_sr:
        wav = ta_resample(wav, orig_freq=sr, new_freq=target_sr)
    return wav, target_sr

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    return float(np.dot(a, b))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav1", required=True)
    ap.add_argument("--wav2", required=True)
    ap.add_argument("--checkpoint", required=False, default=None)
    ap.add_argument("--sample_rate", type=int, default=DEFAULT_SR)
    ap.add_argument("--proj_dim", type=int, default=DEFAULT_PROJ)
    ap.add_argument("--clip_sec", type=float, default=2.0)
    ap.add_argument("--device", default=("cuda" if torch.cuda.is_available() else "cpu"))
    args = ap.parse_args()

    w1 = os.path.abspath(args.wav1)
    w2 = os.path.abspath(args.wav2)
    if not os.path.isfile(w1): raise FileNotFoundError(w1)
    if not os.path.isfile(w2): raise FileNotFoundError(w2)

    if args.checkpoint is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        args.checkpoint = os.path.join(project_root, "models", "audio_encoder", "checkpoints", "checkpoint_last.pt")
    ckpt = os.path.abspath(args.checkpoint)
    if not os.path.isfile(ckpt): raise FileNotFoundError(ckpt)

    device = args.device
    model = Encoder(proj=args.proj_dim).to(device)
    state, _ = load_checkpoint(ckpt, device)
    model.load_state_dict(state)
    model.eval()

    wav1, sr1 = load_wav(w1, target_sr=args.sample_rate)
    wav2, sr2 = load_wav(w2, target_sr=args.sample_rate)

    e1 = compute_embedding(model, wav1, sr1, device=device, clip_sec=args.clip_sec)
    e2 = compute_embedding(model, wav2, sr2, device=device, clip_sec=args.clip_sec)

    sim = cosine(e1, e2)
    print(f"Cosine similarity: {sim:.4f}")
    print("Guideline (rough):")
    print("  ~0.80–0.95: likely same speaker (depends on noise/recording)")
    print("  ~0.20–0.60: mixed/uncertain")
    print("  <0.20: likely different speakers")

if __name__ == "__main__":
    main()
