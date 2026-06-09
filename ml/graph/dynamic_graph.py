from typing import List, Dict, Any
import networkx as nx
from torch_geometric.data import Data
from torch_geometric.utils import to_networkx

def get_graph_density(graph: Data) -> float:
    """Returns edge_count / max_possible_edges for undirected graph."""
    n = graph.num_nodes
    if n <= 1:
        return 0.0
    
    # max possible edges in undirected graph without self-loops: N * (N - 1) / 2
    # but torch geometric edge_index stores undirected edges as two directed edges, so count is E / 2
    # Wait, the edge index might have both (u,v) and (v,u). We just divide by 2 for undirected edges.
    e = graph.edge_index.shape[1] / 2
    max_e = (n * (n - 1)) / 2
    
    return float(e / max_e)

def get_central_nodes(graph: Data, symbols: List[str], top_k: int = 5) -> List[str]:
    """Returns top_k asset symbols by degree centrality (node with most edges)."""
    if graph.edge_index.shape[1] == 0:
        return symbols[:top_k]
        
    G = to_networkx(graph, to_undirected=True)
    degree_dict = dict(G.degree())
    
    # Sort by degree descending
    sorted_nodes = sorted(degree_dict.keys(), key=lambda x: degree_dict[x], reverse=True)
    
    central = []
    for node in sorted_nodes[:top_k]:
        if node < len(symbols):
            central.append(symbols[node])
            
    return central

def get_correlation_clusters(graph: Data, symbols: List[str]) -> Dict[str, List[str]]:
    """
    Returns connected components as dict: cluster_id -> list of symbols.
    """
    if graph.edge_index.shape[1] == 0:
        # Every node is its own cluster
        return {f"cluster_{i}": [symbols[i]] for i in range(len(symbols))}
        
    G = to_networkx(graph, to_undirected=True)
    components = list(nx.connected_components(G))
    
    clusters = {}
    for idx, comp in enumerate(components):
        cluster_syms = [symbols[node] for node in comp if node < len(symbols)]
        if cluster_syms:
            clusters[f"cluster_{idx}"] = cluster_syms
            
    return clusters

def summarize_graph(graph: Data, symbols: List[str]) -> Dict[str, Any]:
    """
    Returns dict with: node_count, edge_count, density, top_central_nodes, cluster_count, avg_edge_weight
    """
    node_count = graph.num_nodes
    edge_count = graph.edge_index.shape[1] // 2 if graph.edge_index.shape[1] > 0 else 0
    density = get_graph_density(graph)
    central_nodes = get_central_nodes(graph, symbols)
    clusters = get_correlation_clusters(graph, symbols)
    
    avg_weight = 0.0
    if graph.edge_attr is not None and graph.edge_attr.numel() > 0:
        avg_weight = float(graph.edge_attr.mean().item())
        
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "density": density,
        "top_central_nodes": central_nodes,
        "cluster_count": len(clusters),
        "avg_edge_weight": avg_weight
    }
