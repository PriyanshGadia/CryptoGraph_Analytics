import torch
import pytest
from torch_geometric.data import Data
from ml.models.stgcn import STGCNModel

def test_model_forward_pass():
    # Setup model parameters
    in_features = 24
    hidden_dim = 64
    num_nodes = 10
    seq_len = 5
    
    model = STGCNModel(
        in_features=in_features,
        hidden_dim=hidden_dim,
        gat_heads_1=4,
        gat_heads_2=2,
        transformer_layers=2,
        transformer_heads=4,
        dropout=0.1
    )
    model.eval()
    
    # Create mock temporal graph sequence
    graph_sequence = []
    for _ in range(seq_len):
        # Generate random node features (num_nodes, in_features)
        x = torch.randn((num_nodes, in_features), dtype=torch.float32)
        # Fully connected graph for 10 nodes -> 90 edges (excluding self-loops)
        edges = []
        weights = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:
                    edges.append([i, j])
                    weights.append([0.8])
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(weights, dtype=torch.float32)
        
        g = Data(x=x, edge_index=edge_index, edge_attr=edge_attr, num_nodes=num_nodes)
        graph_sequence.append(g)
        
    with torch.no_grad():
        dir_logits, vol_logits = model(graph_sequence)
        
    assert dir_logits.shape == (num_nodes, 3), f"Expected direction logits shape (10, 3), got {dir_logits.shape}"
    assert vol_logits.shape == (num_nodes, 4), f"Expected volatility logits shape (10, 4), got {vol_logits.shape}"
    print("ST-GCN model forward pass unit test passed successfully!")


def test_sector_pooling_head_robustness():
    from ml.pipelines.training_pipeline_enterprise import SectorPoolingHead
    
    hidden_dim = 64
    n_sectors = 9
    head = SectorPoolingHead(hidden_dim, n_sectors=n_sectors)
    head.eval()

    # Registered/Default sector assignments buffer (e.g. 100 elements)
    default_assignments = torch.randint(0, n_sectors, (100,), dtype=torch.long)

    # Test cases for different node counts:
    # 1. N_nodes is smaller (e.g. 30 nodes during sub-graph evaluation or validation)
    # 2. N_nodes is equal (100 nodes)
    # 3. N_nodes is larger (e.g. 120 nodes)
    for N_nodes in [30, 100, 120]:
        B = 4
        x = torch.randn(B * N_nodes, hidden_dim)
        
        with torch.no_grad():
            out = head(x, default_assignments, B, N_nodes)
            
        assert out.shape == (B * N_nodes, hidden_dim), (
            f"Expected output shape {(B * N_nodes, hidden_dim)}, got {out.shape} for N_nodes={N_nodes}"
        )
    print("SectorPoolingHead robustness unit tests passed successfully!")

