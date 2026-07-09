import torch
import torch.nn as nn
import torch.nn.functional as F


class CausalConv1dBlock(nn.Module):
    """One dilated causal convolution block with residual connection."""

    def __init__(self, channels: int, kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation  # causal: pad only on the left
        self.conv = nn.Conv1d(channels, channels, kernel_size, padding=self.padding, dilation=dilation)
        self.norm = nn.BatchNorm1d(channels)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (N, C, T)
        out = self.conv(x)
        out = out[:, :, : -self.padding] if self.padding > 0 else out  # strip right-side padding to stay causal
        out = self.norm(out)
        out = F.relu(out)
        out = self.dropout(out)
        return x + out  # residual connection


class TemporalTCN(nn.Module):
    """
    Causal dilated TCN. Input (N, T, hidden_dim) -> Output (N, hidden_dim),
    taking the representation at the final timestep after dilated convolutions
    have given it access to the full receptive field of the sequence.
    """

    def __init__(self, hidden_dim: int, kernel_size: int = 3, dilations=None, dropout: float = 0.1):
        super().__init__()
        # [R8-SPEED-B] Removed dilation=16: receptive field of [1,2,4,8] with
        # kernel_size=3 is 1+2*(3-1)*(1+2+4+8) = 61 days, more than 4x the
        # 14-day lookback_days. The dilation=16 block was wasted compute.
        dilations = dilations or [1, 2, 4, 8]
        self.blocks = nn.ModuleList([
            CausalConv1dBlock(hidden_dim, kernel_size, d, dropout) for d in dilations
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (N, T, hidden_dim) -> (N, hidden_dim, T) for Conv1d
        x = x.transpose(1, 2)
        for block in self.blocks:
            x = block(x)
        # Take the representation at the final (most recent) timestep
        return x[:, :, -1]
