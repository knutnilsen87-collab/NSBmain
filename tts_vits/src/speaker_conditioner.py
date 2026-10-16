import torch
import torch.nn as nn

class SpeakerConditioner(nn.Module):
    def __init__(self, emb_dim: int, hidden_dim: int):
        super().__init__()
        self.proj = nn.Linear(emb_dim, hidden_dim)

    def forward(self, emb: torch.Tensor) -> torch.Tensor:
        # emb: [B, emb_dim] -> [B, hidden_dim]
        return self.proj(emb)
