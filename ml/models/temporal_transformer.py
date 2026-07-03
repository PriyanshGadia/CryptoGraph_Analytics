import math
import torch
import torch.nn as nn
from torch import Tensor

class TemporalTransformer(nn.Module):
    """
    Processes time dimension of stacked node embeddings with learnable
    positional encoding and attention-weighted pooling.

    Input:  (N, T, hidden_dim)  - N nodes, T timesteps
    Output: (N, hidden_dim)     - aggregated temporal representation
    """
    def __init__(
        self,
        hidden_dim: int = 128,
        nhead: int = 8,
        num_layers: int = 4,
        dropout: float = 0.1,
        max_len: int = 500
    ):
        super().__init__()
        # Learnable positional encoding (better for short sequences T=14-30)
        self.pos_embedding = nn.Parameter(torch.randn(1, max_len, hidden_dim) * 0.02)
        self.pos_dropout = nn.Dropout(p=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Attention-weighted temporal pooling instead of last-timestep-only
        self.pool_query = nn.Parameter(torch.randn(1, 1, hidden_dim) * 0.02)
        self.pool_attn = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=nhead,
            dropout=dropout,
            batch_first=True
        )
        self.pool_norm = nn.LayerNorm(hidden_dim)

    def forward(self, x: Tensor) -> Tensor:
        """
        x: (N, T, hidden_dim)
        1. Add learnable positional encoding
        2. Pass through TransformerEncoder
        3. Attention-weighted pooling across all timesteps
        Returns: (N, hidden_dim)
        """
        N, T, D = x.shape

        # Learnable positional encoding
        x = x + self.pos_embedding[:, :T, :]
        x = self.pos_dropout(x)

        # Transformer encoder
        out = self.transformer(x)  # (N, T, D)

        # Attention-weighted pooling: learned query attends over all timesteps
        query = self.pool_query.expand(N, -1, -1)  # (N, 1, D)
        pooled, _ = self.pool_attn(query, out, out)  # (N, 1, D)
        pooled = self.pool_norm(pooled.squeeze(1))   # (N, D)

        return pooled
