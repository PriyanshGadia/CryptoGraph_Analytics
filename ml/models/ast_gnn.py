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
        
        # Compute dot-product attention
        attn = torch.matmul(q, k.t()) / self.scale  # (N, N)
        # Apply ReLU + Softmax to produce non-negative, normalized weights
        return F.softmax(F.relu(attn), dim=-1)

class AdaptiveRelationalGNN(nn.Module):
    """
    Hybrid Spatio-Temporal Layer that combines:
    1. Sparse RGATConv (Relational GAT) over the physical graph (Sector, Cap, Correlation)
    2. Dense learned message-passing over the Dynamic Adaptive Graph.
    
    Supports vectorized execution across multiple graph snapshots simultaneously for speed.
    """
    def __init__(self, hidden_dim: int = 128, num_relations: int = 3, heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.hidden_dim = hidden_dim
        
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

    def forward(self, x: Tensor, edge_index: Tensor, edge_type: Tensor, edge_attr: Tensor, T: int = 1, N: int = None) -> Tensor:
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
        
        # Step 2: Dense message passing over the learned adaptive graph (vectorized across snapshots)
        if T > 1 and N is not None:
            # Reshape x to (T, N, hidden_dim) for batched query-key attention
            # The contiguous order in PyG Batch is snapshots first: [t0_n0, t0_n1, ..., t1_n0, ...]
            x_3d = x.view(T, N, -1)
            q = self.adaptive_generator.query_projection(x_3d)  # (T, N, d)
            k = self.adaptive_generator.key_projection(x_3d)    # (T, N, d)
            
            # Batch matrix multiplication: (T, N, d) x (T, d, N) -> (T, N, N)
            attn = torch.matmul(q, k.transpose(-2, -1)) / self.adaptive_generator.scale
            A_adapt = F.softmax(F.relu(attn), dim=-1)           # (T, N, N)
            
            h_adaptive = torch.matmul(A_adapt, x_3d)           # (T, N, hidden_dim)
            h_adaptive = h_adaptive.view(N * T, -1)             # (N * T, hidden_dim)
        else:
            A_adapt = self.adaptive_generator(x)  # (N, N)
            h_adaptive = torch.matmul(A_adapt, x)  # (N, hidden_dim)
            
        h_adaptive = self.elu(self.adaptive_weight(h_adaptive))
        
        # Step 3: LayerNorm and Fusion (Residual Connection)
        out = self.norm(x + self.dropout(h_physical + h_adaptive))
        return out
