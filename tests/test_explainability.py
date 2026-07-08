"""
Unit test for GNN Gradient Attribution (Integrated Gradients) feature importance module.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

import pytest
import torch
from torch_geometric.data import Data
from ml.models.stgcn import STGCNModel
from app.ml.gnn_attribution_explainer import GNNGradientAttributionExplainer

def test_gnn_gradient_attribution():
    model = STGCNModel(
        in_features=24,
        hidden_dim=32,
        gat_heads_1=2,
        gat_heads_2=1,
        transformer_layers=2,
        transformer_heads=4,
        dropout=0.1,
        num_direction_classes=3,
        num_volatility_classes=4,
        use_tcn=True
    )
    model.eval()

    # Create dummy graph sequence
    N, T, F = 5, 10, 24
    graph_seq = []
    edge_index = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=torch.long)
    for _ in range(T):
        x = torch.randn(N, F)
        graph_seq.append(Data(x=x, edge_index=edge_index))

    feature_names = [f"feat_{i}" for i in range(F)]
    explainer = GNNGradientAttributionExplainer()

    res = explainer.explain_prediction(
        symbol="BTC",
        features={},
        model=model,
        graph_sequence=graph_seq,
        asset_idx=0,
        feature_names=feature_names
    )

    assert "attributions_pct" in res
    assert len(res["attributions_pct"]) == F
    total_pct = sum(res["attributions_pct"].values())
    assert abs(total_pct - 100.0) < 1.0
