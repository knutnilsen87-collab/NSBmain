import torch
import torch.nn as nn
import torch.nn.functional as F

class Encoder(nn.Module):
    """
    Must match training architecture in train_audio_encoder_v2.py.
    Conv1d stack -> adaptive avg pool -> projection -> L2 normalize.
    """
    def __init__(self, proj: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(1, 64, 5, 2, 2), nn.BatchNorm1d(64), nn.GELU(),
            nn.Conv1d(64, 128, 5, 2, 2), nn.BatchNorm1d(128), nn.GELU(),
            nn.Conv1d(128, 256, 5, 2, 2), nn.BatchNorm1d(256), nn.GELU(),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.proj = nn.Sequential(
            nn.Linear(256, 256), nn.GELU(),
            nn.Linear(256, proj)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, 1, T]
        h = self.net(x)
        h = self.pool(h).squeeze(-1)  # [B, 256]
        z = self.proj(h)              # [B, proj]
        return F.normalize(z, dim=-1)
