import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.data import Batch

from ml.models.heads import MultiTaskHead
from ml.models.temporal_transformer import TemporalTransformer
from ml.models.gat_temporal import SpatioTemporalGAT
from ml.models.causal_tcn import TemporalTCN

class STGCNModel(nn.Module):
    """
    Full ST-GCN model assembling all components (Adaptive RGNN + Causal TCN / Transformer).

    Architecture:
      Input (T graph snapshots)
        -> PyG Batch compilation (Vectorized representation)
        -> LinearProjection: (N * T, in_features) -> (N * T, hidden_dim)
        -> SpatioTemporalGAT (Relation-Aware + Adaptive): Vectorized convolutions -> (N, T, hidden_dim)
        -> TemporalTCN or TemporalTransformer: (N, T, hidden_dim) -> (N, hidden_dim)
        -> MultiTaskHead: (N, hidden_dim) -> direction (N,3) + volatility (N,4)
    """

    def __init__(
        self,
        in_features: int = 24,
        hidden_dim: int = 32,
        gat_heads_1: int = 2,
        gat_heads_2: int = 1,
        transformer_layers: int = 2,
        transformer_heads: int = 4,
        dropout: float = 0.1,
        num_direction_classes: int = 3,
        num_volatility_classes: int = 4,
        use_tcn: bool = True,
        **kwargs
    ):
        super().__init__()
        # Store config for save/load
        self.config = {
            "in_features": in_features,
            "hidden_dim": hidden_dim,
            "gat_heads_1": gat_heads_1,
            "gat_heads_2": gat_heads_2,
            "transformer_layers": transformer_layers,
            "transformer_heads": transformer_heads,
            "dropout": dropout,
            "num_direction_classes": num_direction_classes,
            "num_volatility_classes": num_volatility_classes,
            "use_tcn": use_tcn,
            **kwargs
        }
        self.projection = nn.Linear(in_features, hidden_dim)
        self.spatial_gat = SpatioTemporalGAT(hidden_dim, gat_heads_1, gat_heads_2, dropout)
        
        # Select temporal encoder
        if use_tcn:
            self.temporal_encoder = TemporalTCN(hidden_dim, kernel_size=3, dilations=[1, 2, 4, 8], dropout=dropout)
        else:
            self.temporal_encoder = TemporalTransformer(hidden_dim, transformer_heads,
                                                       transformer_layers, dropout)
            
        self.head = MultiTaskHead(hidden_dim, dropout, num_direction_classes, num_volatility_classes)

    def forward(
        self,
        graph_sequence: list,
        return_all: bool = False
    ) -> tuple:
        """
        Runs full spatio-temporal convolutions in a fully vectorized pipeline.
        
        Returns: (direction_logits (N,3), volatility_logits (N,4)) or all four outputs
        """
        T = len(graph_sequence)
        if T == 0:
            # Empty fallback
            N = 0
            device = next(self.parameters()).device
            return torch.empty((0, 3), device=device), torch.empty((0, 4), device=device)
            
        # 1. Ensure all graph snapshots have edge_type set
        for graph in graph_sequence:
            if not hasattr(graph, "edge_type") or graph.edge_type is None:
                graph.edge_type = torch.zeros(graph.edge_index.shape[1], dtype=torch.long, device=graph.edge_index.device)
                
        # 2. Vectorized batch compilation
        batched_graph = Batch.from_data_list(graph_sequence)
        
        # 3. Vectorized projection pass (no cloning, no loops!)
        batched_graph.x = F.relu(self.projection(batched_graph.x))
        
        # 4. SpatioTemporalGAT convolutions
        node_embeds = self.spatial_gat(batched_graph)  # (N, T, hidden_dim)
        
        # 5. Temporal Encoder & Task Heads
        temporal_embeds = self.temporal_encoder(node_embeds)  # (N, hidden_dim)
        return self.head(temporal_embeds, return_all=return_all)

    def save(self, path: str) -> None:
        """Save model weights and config to path."""
        torch.save({
            "model_state_dict": self.state_dict(),
            "config": self.config
        }, path)

    @classmethod
    def load(cls, path: str, map_location: str = "cpu") -> "STGCNModel":
        """Load model from saved checkpoint."""
        checkpoint = torch.load(path, map_location=map_location, weights_only=False)
        model = cls(**checkpoint["config"])
        model.load_state_dict(checkpoint["model_state_dict"])
        return model
