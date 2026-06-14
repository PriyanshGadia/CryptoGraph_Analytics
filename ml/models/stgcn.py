import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.data import Data

from ml.models.heads import MultiTaskHead
from ml.models.temporal_transformer import TemporalTransformer
from ml.models.gat_temporal import SpatioTemporalGAT

class STGCNModel(nn.Module):
    """
    Full ST-GCN model assembling all components.

    Architecture:
      Input (N, 24/27 features)
        -> LinearProjection: (N, in_features) -> (N, 128)
        -> SpatioTemporalGAT: processes T graph snapshots -> (N, T, 128)
        -> TemporalTransformer: (N, T, 128) -> (N, 128)
        -> MultiTaskHead: (N, 128) -> direction (N,5) + volatility (N,4)
    """

    def __init__(
        self,
        in_features: int = 24,
        hidden_dim: int = 128,
        gat_heads_1: int = 8,
        gat_heads_2: int = 4,
        transformer_layers: int = 4,
        transformer_heads: int = 8,
        dropout: float = 0.1,
        num_direction_classes: int = 5,
        num_volatility_classes: int = 4
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
            "num_volatility_classes": num_volatility_classes
        }
        self.projection = nn.Linear(in_features, hidden_dim)
        self.spatial_gat = SpatioTemporalGAT(hidden_dim, gat_heads_1, gat_heads_2, dropout)
        self.temporal_tf = TemporalTransformer(hidden_dim, transformer_heads,
                                               transformer_layers, dropout)
        self.head = MultiTaskHead(hidden_dim, dropout)

    def forward(
        self,
        graph_sequence: list
    ) -> tuple[Tensor, Tensor]:
        """
        1. Project input features for each graph in sequence
           [graph.x is (N, in_features)] -> projected to (N, 128) for each graph
        2. Pass projected sequence through SpatioTemporalGAT -> (N, T, 128)
        3. Pass through TemporalTransformer -> (N, 128)
        4. Pass through MultiTaskHead -> (direction_logits, volatility_logits)
        Returns: (direction_logits (N,5), volatility_logits (N,4))
        """
        projected_sequence = []
        for graph in graph_sequence:
            projected_graph = graph.clone()
            projected_graph.x = F.relu(self.projection(graph.x))
            projected_sequence.append(projected_graph)

        node_embeds = self.spatial_gat(projected_sequence)  # (N, T, 128)
        temporal_embeds = self.temporal_tf(node_embeds)     # (N, 128)
        return self.head(temporal_embeds)

    def save(self, path: str) -> None:
        """Save model weights and config to path."""
        torch.save({
            "model_state_dict": self.state_dict(),
            "config": self.config
        }, path)

    @classmethod
    def load(cls, path: str, map_location: str = "cpu") -> "STGCNModel":
        """Load model from saved checkpoint."""
        checkpoint = torch.load(path, map_location=map_location)
        model = cls(**checkpoint["config"])
        model.load_state_dict(checkpoint["model_state_dict"])
        return model
