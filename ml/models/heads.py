import torch.nn as nn
from torch import Tensor

DIRECTION_CLASSES  = ["strong_up", "up", "neutral", "down", "strong_down"]
VOLATILITY_CLASSES = ["low", "medium", "high", "extreme"]

class MultiTaskHead(nn.Module):
    """Two independent prediction heads sharing the same input representation."""

    def __init__(self, input_dim: int = 128, dropout: float = 0.2):
        super().__init__()
        # Direction head: 5-class (strong_up, up, neutral, down, strong_down)
        self.direction_head = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 5)
        )
        # Volatility head: 4-class (low, medium, high, extreme)
        self.volatility_head = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 4)
        )

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor]:
        """Returns (direction_logits shape (N,5), volatility_logits shape (N,4))"""
        return self.direction_head(x), self.volatility_head(x)
