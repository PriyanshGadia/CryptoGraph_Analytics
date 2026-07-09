import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import RGATConv

class AdaptiveAdjacencyGenerator(nn.Module):
    """
    Generates a dynamic, feature-dependent soft adjacency matrix (N, N)
    using self-attention query-key mapping.
    """
    def __init__(self, hidden_dim: int = 128):
        super().__init__()
        self.query_projection = nn.Linear(hidden_dim, hidden_dim // 4)
        self.key_projection = nn.Linear(hidden_dim, hidden_dim // 4)
        self.scale = (hidden_dim // 4) ** 0.5

    def forward(self, x: Tensor) -> Tensor:
        """
        x: (N, hidden_dim)
        Returns: (N, N) soft adjacency weights
        """
        q = self.query_projection(x)  # (N, d)
        k = self.key_projection(x)    # (N, d)
        attn = torch.matmul(q, k.t()) / self.scale  # (N, N)
        return F.softmax(F.relu(attn), dim=-1)

class AdaptiveRelationalGNN(nn.Module):
    """
    Hybrid Spatio-Temporal Layer that combines:
    1. Sparse RGATConv (Relational GAT) over the physical graph (Sector, Cap, Correlation)
    2. Dense learned message-passing over the Dynamic Adaptive Graph.

    [R8-SPEED-A] Adaptive adjacency is now computed in chunks of `adaptive_chunk`
    snapshots to prevent OOM and reduce peak GPU memory from O(B*T*N^2) to
    O(chunk*N^2). With B=32, T=14, N=100: old peak = 45M floats (180MB),
    new peak = 4M floats (16MB) at chunk=32.
    """
    def __init__(self, hidden_dim: int = 128, num_relations: int = 3,
                 heads: int = 4, dropout: float = 0.1, adaptive_chunk: int = 32):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.adaptive_chunk = adaptive_chunk

        # 1. Physical Graph Relational Conv
        self.rgat = RGATConv(
            in_channels=hidden_dim,
            out_channels=hidden_dim // heads,
            num_relations=num_relations,
            heads=heads,
            concat=True,
            dropout=dropout,
            edge_dim=1
        )

        # 2. Adaptive Graph Layer
        self.adaptive_generator = AdaptiveAdjacencyGenerator(hidden_dim)
        self.adaptive_weight = nn.Linear(hidden_dim, hidden_dim)

        # 3. LayerNorm and Fusion
        self.norm = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(dropout)
        self.elu = nn.ELU()

    def _adaptive_pass_chunked(self, x: Tensor, T: int, N: int) -> Tensor:
        """
        [R8-SPEED-A] Chunked adaptive graph pass.

        Splits the T_total snapshots into blocks of size `adaptive_chunk`
        and processes each block independently. This reduces peak GPU memory
        from O(T_total * N^2) to O(chunk * N^2) at the cost of a Python loop.

        For B=32, T=14, N=100, chunk=32: processes 7 chunks of 32 snapshots,
        each allocating 32*100*100*4 = 12.8 MB vs the original 448*100*100*4 = 179 MB.
        """
        x_3d = x.view(T, N, -1)          # (T, N, hidden)
        chunks = []
        q_proj = self.adaptive_generator.query_projection
        k_proj = self.adaptive_generator.key_projection
        scale = self.adaptive_generator.scale

        for start in range(0, T, self.adaptive_chunk):
            end = min(start + self.adaptive_chunk, T)
            x_chunk = x_3d[start:end]                         # (chunk, N, hidden)
            q = q_proj(x_chunk)                               # (chunk, N, d)
            k = k_proj(x_chunk)                               # (chunk, N, d)
            attn = torch.matmul(q, k.transpose(-2, -1)) / scale  # (chunk, N, N)
            A = F.softmax(F.relu(attn), dim=-1)               # (chunk, N, N)
            h = torch.matmul(A, x_chunk)                      # (chunk, N, hidden)
            chunks.append(h)

        h_adaptive = torch.cat(chunks, dim=0)                 # (T, N, hidden)
        return h_adaptive.view(N * T, -1)                     # (N*T, hidden)

    def forward(self, x: Tensor, edge_index: Tensor, edge_type: Tensor,
                edge_attr: Tensor, T: int = 1, N: int = None) -> Tensor:
        """
        x: (N * T, hidden_dim)
        edge_index: (2, E_physical)
        edge_type: (E_physical,)
        edge_attr: (E_physical, 1)
        T: number of graph snapshots in the sequence
        N: number of nodes per snapshot
        """
        # Step 1: Relational Graph Attention over the physical multi-relation graph
        h_physical = self.rgat(x, edge_index, edge_type, edge_attr=edge_attr)  # (N * T, hidden_dim)
        h_physical = self.elu(h_physical)

        # Step 2: Dense message passing over the learned adaptive graph
        if T > 1 and N is not None:
            # [R8-SPEED-A] Use chunked computation to avoid allocating full (T, N, N) tensor
            h_adaptive = self._adaptive_pass_chunked(x, T, N)
        else:
            A_adapt = self.adaptive_generator(x)   # (N, N)
            h_adaptive = torch.matmul(A_adapt, x)  # (N, hidden_dim)

        h_adaptive = self.elu(self.adaptive_weight(h_adaptive))

        # Step 3: LayerNorm and Fusion (Residual Connection)
        out = self.norm(x + self.dropout(h_physical + h_adaptive))
        return out
