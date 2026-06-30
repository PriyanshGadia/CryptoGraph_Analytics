import torch
import torch.nn as nn
from torch import Tensor
from torch_geometric.nn import GATv2Conv

class SpatioTemporalGAT(nn.Module):
    """
    Applies GATv2Conv to each timestep independently, then stacks embeddings.
    Input:  list of T Data objects, each with x shape (N, hidden_dim)
    Output: tensor shape (N, T, hidden_dim)
    """
    def __init__(
        self,
        hidden_dim: int = 128,
        heads_1: int = 8,
        heads_2: int = 4,
        dropout: float = 0.1
    ):
        super().__init__()
        self.gat1 = GATv2Conv(
            in_channels=hidden_dim,
            out_channels=hidden_dim // heads_1,
            heads=heads_1,
            concat=True,
            dropout=dropout,
            edge_dim=1
        )
        self.gat2 = GATv2Conv(
            in_channels=hidden_dim,
            out_channels=hidden_dim,
            heads=heads_2,
            concat=False,
            dropout=dropout,
            edge_dim=1
        )
        self.elu = nn.ELU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, graph_sequence: list) -> Tensor:
        """
        For each Data object in graph_sequence:
          h = gat1(x, edge_index, edge_attr) -> ELU -> dropout
          h = gat2(h, edge_index, edge_attr) -> ELU -> dropout
        Stack all T outputs -> (N, T, hidden_dim)
        """
        embeddings = []
        for graph in graph_sequence:
            edge_index = graph.edge_index
            edge_attr = graph.edge_attr
            h = self.elu(self.gat1(graph.x, edge_index, edge_attr=edge_attr))
            h = self.dropout(h)
            h = self.elu(self.gat2(h, edge_index, edge_attr=edge_attr))
            h = self.dropout(h)
            embeddings.append(h)  # (N, hidden_dim)
        return torch.stack(embeddings, dim=1)  # (N, T, hidden_dim)
