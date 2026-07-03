import torch
import torch.nn as nn
from torch import Tensor
from torch_geometric.data import Batch
from ml.models.ast_gnn import AdaptiveRelationalGNN

class SpatioTemporalGAT(nn.Module):
    """
    Applies relation-aware GNN with learned adaptive relationships to each timestep
    independently in a single vectorized forward pass, then reshapes embeddings.

    Input:  list of T Data objects or a pre-compiled PyG Batch object.
    Output: tensor shape (N, T, hidden_dim)
    """
    def __init__(
        self,
        hidden_dim: int = 128,
        heads_1: int = 4,
        heads_2: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()
        # 3 physical relations (Sector=0, Cap=1, Correlation=2)
        self.rgat1 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim,
            num_relations=3,
            heads=heads_1,
            dropout=dropout
        )
        self.rgat2 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim,
            num_relations=3,
            heads=heads_2,
            dropout=dropout
        )

    def forward(self, graph_sequence) -> Tensor:
        """
        Batch all T graph snapshots and pass through rgat1 and rgat2 in one single call.
        """
        if isinstance(graph_sequence, list):
            T = len(graph_sequence)
            if T == 0:
                return torch.empty((0, 0, self.rgat1.hidden_dim))
                
            N = graph_sequence[0].num_nodes
            
            # Batch snapshots into a single disjoint multi-relation graph
            for graph in graph_sequence:
                if not hasattr(graph, "edge_type") or graph.edge_type is None:
                    graph.edge_type = torch.zeros(graph.edge_index.shape[1], dtype=torch.long, device=graph.edge_index.device)
            
            batched_graph = Batch.from_data_list(graph_sequence)
        else:
            # Pre-batched PyG Batch input
            batched_graph = graph_sequence
            T = batched_graph.num_graphs
            N = batched_graph.x.shape[0] // T
            
        # Perform multi-relational spatial convolutions in a single call (no python loop!)
        h = batched_graph.x
        h = self.rgat1(h, batched_graph.edge_index, batched_graph.edge_type, edge_attr=batched_graph.edge_attr, T=T, N=N)
        h = self.rgat2(h, batched_graph.edge_index, batched_graph.edge_type, edge_attr=batched_graph.edge_attr, T=T, N=N)
        
        # Reshape batched output back to (N, T, hidden_dim)
        h = h.view(T, N, -1).transpose(0, 1)  # (N, T, hidden_dim)
        return h
