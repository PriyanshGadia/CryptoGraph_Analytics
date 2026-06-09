import math
import torch
import torch.nn as nn
from torch import Tensor

class SinusoidalPositionalEncoding(nn.Module):
    """Standard sinusoidal positional encoding."""
    def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, 1, d_model)
        pe[:, 0, 0::2] = torch.sin(position * div_term)
        pe[:, 0, 1::2] = torch.cos(position * div_term)
        # Shape: (max_len, 1, d_model) => we want it (1, max_len, d_model) for batch_first=True
        self.register_buffer('pe', pe.transpose(0, 1))

    def forward(self, x: Tensor) -> Tensor:
        """x shape: (batch, seq_len, d_model) -> add positional encoding"""
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)

class TemporalTransformer(nn.Module):
    """
    Processes time dimension of stacked node embeddings.
    Input:  (N, T, hidden_dim)  - N nodes, T timesteps
    Output: (N, hidden_dim)     - representation at final timestep
    """
    def __init__(
        self,
        hidden_dim: int = 128,
        nhead: int = 8,
        num_layers: int = 4,
        dropout: float = 0.1
    ):
        super().__init__()
        self.pos_encoding = SinusoidalPositionalEncoding(hidden_dim, dropout=dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

    def forward(self, x: Tensor) -> Tensor:
        """
        x: (N, T, hidden_dim)
        1. Add positional encoding
        2. Pass through TransformerEncoder
        3. Return only last timestep: output[:, -1, :]
        Returns: (N, hidden_dim)
        """
        x = self.pos_encoding(x)
        out = self.transformer(x)
        return out[:, -1, :]
