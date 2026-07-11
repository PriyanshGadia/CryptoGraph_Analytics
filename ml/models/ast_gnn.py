import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import RGATConv, GATv2Conv

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
                 heads: int = 4, dropout: float = 0.1, adaptive_chunk: int = 32,
                 use_gatv2: bool = False, rgat_chunk: int = 0):
        """
        use_gatv2: if True, use a memory-efficient GATv2Conv instead of RGATConv.
                   GATv2 has no per-edge weight matrix (O(E*heads*d) vs O(E*heads*d^2)),
                   making it ~32x cheaper in VRAM for hidden_dim=64.
        rgat_chunk: if > 0, process the RGAT pass in temporal chunks of this many
                    snapshots to cap peak edge count. 0 = no chunking (full batch at once).
        """
        super().__init__()
        self.hidden_dim = hidden_dim
        self.adaptive_chunk = adaptive_chunk
        self.rgat_chunk = rgat_chunk
        self.use_gatv2 = use_gatv2

        # 1. Physical Graph Relational/Attention Conv
        if use_gatv2:
            # GATv2Conv: no per-edge weight matrix → ~32× less VRAM on the bmm step
            # edge_dim accepted by GATv2Conv as a linear fill on edge features
            self.rgat = GATv2Conv(
                in_channels=hidden_dim,
                out_channels=hidden_dim // heads,
                heads=heads,
                concat=True,
                dropout=dropout,
                edge_dim=1,
                add_self_loops=False,
            )
        else:
            self.rgat = RGATConv(
                in_channels=hidden_dim,
                out_channels=hidden_dim // heads,
                num_relations=num_relations,
                heads=heads,
                concat=True,
                dropout=dropout,
                edge_dim=1,
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

    def _rgat_pass(self, x: Tensor, edge_index: Tensor, edge_type: Tensor,
                   edge_attr: Tensor, T: int, N: int) -> Tensor:
        """
        Run the RGAT/GATv2 conv, optionally in temporal chunks to cap peak VRAM.

        With rgat_chunk=0 (default) the full (T*N, hidden) tensor is processed
        at once — same behaviour as before.
        With rgat_chunk=C, we split the T snapshots into blocks of C, build a
        sub-batch for each block, run conv, then cat the outputs. This reduces
        peak edge-count from E_total to E_chunk ≈ E_total * C / T.
        """
        if self.rgat_chunk <= 0 or T <= self.rgat_chunk:
            # No chunking — single forward pass
            if self.use_gatv2:
                return self.rgat(x, edge_index, edge_attr=edge_attr)
            return self.rgat(x, edge_index, edge_type, edge_attr=edge_attr)

        # Chunked path: split on the temporal axis
        # edge_index/edge_type/edge_attr are block-diagonal across T snapshots.
        # Each snapshot contributes edges for node range [t*N, (t+1)*N).
        chunks_out = []
        for t_start in range(0, T, self.rgat_chunk):
            t_end = min(t_start + self.rgat_chunk, T)
            # Node indices in this chunk
            n_start = t_start * N
            n_end   = t_end   * N
            # Mask edges belonging to this snapshot range
            src = edge_index[0]
            mask = (src >= n_start) & (src < n_end)
            ei_chunk  = edge_index[:, mask] - n_start  # re-zero indices
            ea_chunk  = edge_attr[mask] if edge_attr is not None else None
            et_chunk  = edge_type[mask] if (edge_type is not None and not self.use_gatv2) else None
            x_chunk   = x[n_start:n_end]
            if self.use_gatv2:
                h_chunk = self.rgat(x_chunk, ei_chunk, edge_attr=ea_chunk)
            else:
                h_chunk = self.rgat(x_chunk, ei_chunk, et_chunk, edge_attr=ea_chunk)
            chunks_out.append(h_chunk)
        return torch.cat(chunks_out, dim=0)

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
        # Step 1: Relational/Attention Graph Conv over the physical multi-relation graph
        h_physical = self._rgat_pass(x, edge_index, edge_type, edge_attr, T, N or 1)
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
