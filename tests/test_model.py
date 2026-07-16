import pytest

try:
    import torch
    from torch_geometric.data import Data
    from ml.models.stgcn import STGCNModel
    has_geometric = True
except ImportError:
    has_geometric = False

pytestmark = pytest.mark.skipif(not has_geometric, reason="torch_geometric is not installed")

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


def test_enterprise_model_batched_forward_pass():
    from ml.pipelines.training_pipeline_enterprise import (
        TrainingConfig, EnterpriseSTGCNModel, graph_collate_fn
    )
    
    config = TrainingConfig()
    config.hidden_dim = 32
    config.batch_size = 2
    config.lookback_days = 5
    config.feature_dim = 24
    
    model = EnterpriseSTGCNModel(config)
    model.eval()
    
    # 100 nodes, 24 features
    num_nodes = 100
    available_symbols = [f"SYM{i}" for i in range(num_nodes)]
    model.set_sectors(available_symbols)
    
    # Create mock batch of sequences
    # Batch size = 2, lookback_days = 5
    batch_data = []
    for b in range(2):
        seq = []
        for t in range(5):
            x = torch.randn((num_nodes, config.feature_dim), dtype=torch.float32)
            # Some random edges
            edges = torch.randint(0, num_nodes, (2, 50), dtype=torch.long)
            edge_type = torch.randint(0, 3, (50,), dtype=torch.long)
            edge_attr = torch.randn((50, 1), dtype=torch.float32)
            g = Data(x=x, edge_index=edges, edge_type=edge_type, edge_attr=edge_attr, num_nodes=num_nodes)
            seq.append(g)
        
        # Target returns for this sequence (num_nodes,)
        target = torch.randn(num_nodes, dtype=torch.float32)
        mask = torch.ones(num_nodes, dtype=torch.float32)
        batch_data.append((seq, target, mask))
        
    # Collate
    batched_graphs, targets, masks = graph_collate_fn(batch_data)
    
    with torch.no_grad():
        preds, log_vars = model(batched_graphs, return_uncertainty=True)
        
    assert preds.shape == (2, num_nodes)
    assert log_vars.shape == (2, num_nodes)
    print("EnterpriseSTGCNModel batched forward pass unit test passed successfully!")


def test_adaptive_gnn_chunking_equivalence():
    from ml.models.ast_gnn import AdaptiveRelationalGNN
    
    hidden_dim = 16
    num_nodes = 5
    T = 8
    
    model = AdaptiveRelationalGNN(
        hidden_dim=hidden_dim,
        num_relations=3,
        heads=2,
        dropout=0.0,
        use_gatv2=False
    )
    model.eval()
    
    # Create input: T=8 snapshots of 5 nodes
    x = torch.randn(T * num_nodes, hidden_dim)
    
    # We construct a block-diagonal edge_index
    # and random edge types / attributes.
    edges_list = []
    edge_types_list = []
    edge_attrs_list = []
    
    for t in range(T):
        offset = t * num_nodes
        # Generate some physical connections within each snapshot
        edges_t = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 0]], dtype=torch.long) + offset
        edges_list.append(edges_t)
        edge_types_list.append(torch.tensor([0, 1, 2, 0], dtype=torch.long))
        edge_attrs_list.append(torch.randn((4, 1), dtype=torch.float32))
        
    edge_index = torch.cat(edges_list, dim=1)
    edge_type = torch.cat(edge_types_list, dim=0)
    edge_attr = torch.cat(edge_attrs_list, dim=0)
    
    with torch.no_grad():
        # 1. Forward with max_chunk_T = 3 (this triggers chunked execution with chunks: 3, 3, 2)
        out_chunked = model(x, edge_index, edge_type, edge_attr, T=T, N=num_nodes, max_chunk_T=3)
        
        # 2. Forward with max_chunk_T = 10 (this triggers standard non-chunked execution)
        out_non_chunked = model(x, edge_index, edge_type, edge_attr, T=T, N=num_nodes, max_chunk_T=10)
        
    # Verify outputs are mathematically identical
    assert torch.allclose(out_chunked, out_non_chunked, atol=1e-5), (
        f"Chunked and non-chunked forward passes differed! max diff: {(out_chunked - out_non_chunked).abs().max()}"
    )
    print("AdaptiveRelationalGNN chunking equivalence unit test passed successfully!")


