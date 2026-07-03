import torch.nn as nn
from torch import Tensor

DIRECTION_CLASSES  = ["down", "neutral", "up"]
VOLATILITY_CLASSES = ["low", "medium", "high", "extreme"]

class MultiTaskHead(nn.Module):
    """Two prediction heads for classification, plus two auxiliary heads
    for regression (returns & volatility) to act as multi-task regularizers during training.
    """

    def __init__(
        self,
        input_dim: int = 128,
        dropout: float = 0.2,
        num_direction_classes: int = 3,
        num_volatility_classes: int = 4
    ):
        super().__init__()
        # 1. Direction classification head: 3-class (down, neutral, up)
        self.direction_head = nn.Sequential(
            nn.Linear(input_dim, input_dim),
            nn.BatchNorm1d(input_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(input_dim, input_dim // 2),
            nn.BatchNorm1d(input_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(input_dim // 2, num_direction_classes)
        )
        # 2. Volatility classification head: 4-class (low, medium, high, extreme)
        self.volatility_head = nn.Sequential(
            nn.Linear(input_dim, input_dim // 2),
            nn.BatchNorm1d(input_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(input_dim // 2, num_volatility_classes)
        )
        # 3. Auxiliary 1-day Return regression head
        self.reg_returns_head = nn.Sequential(
            nn.Linear(input_dim, input_dim // 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(input_dim // 4, 1)
        )
        # 4. Auxiliary 7-day Volatility regression head
        self.reg_vol_head = nn.Sequential(
            nn.Linear(input_dim, input_dim // 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(input_dim // 4, 1)
        )

    def forward(self, x: Tensor, return_all: bool = False) -> tuple:
        """
        If return_all is True: returns (dir_logits, vol_logits, reg_returns, reg_vol)
        Otherwise: returns (dir_logits, vol_logits) (for backward-compatibility at inference)
        """
        dir_logits = self.direction_head(x)
        vol_logits = self.volatility_head(x)
        if return_all:
            reg_returns = self.reg_returns_head(x).squeeze(-1)
            reg_vol = self.reg_vol_head(x).squeeze(-1)
            return dir_logits, vol_logits, reg_returns, reg_vol
        return dir_logits, vol_logits
