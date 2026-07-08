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
