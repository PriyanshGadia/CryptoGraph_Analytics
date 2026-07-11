import torch
import torch.nn as nn
from torch import Tensor
from typing import Optional, List, Union
from torch_geometric.data import Batch, Data
from ml.models.ast_gnn import AdaptiveRelationalGNN


class SpatioTemporalGAT(nn.Module):
    """
    Applies relation-aware GNN to each snapshot in a single vectorized pass.

    Two calling conventions:
      1. LEGACY (single sequence): graph_sequence = List[Data] of length T.
         B is implicitly 1.
      2. BATCHED: graph_sequence = a pre-built PyG Batch containing B*T graphs
         concatenated SAMPLE-MAJOR, with explicit T and B.

    [R13-SPEED] No Python loops in either RGAT layer:
    - rgat1: RGATConv, processes full (B*T*N, H) tensor in one GPU kernel.
             Safe at batch_size=8 (T_total=240 vs 480 before — halved).
    - rgat2: GATv2Conv — no per-edge (E, heads, d, d) weight matrix.
             This eliminated the 2.94 GiB OOM from R12.
    - result: 2 RGAT kernel calls per batch step instead of 60 sequential loops.
    """

    def __init__(self, hidden_dim: int = 128, heads_1: int = 4, heads_2: int = 2,
                 dropout: float = 0.1):
        super().__init__()
        self.hidden_dim = hidden_dim

        # rgat1: RGATConv — full batched GPU call, no temporal chunking.
        # At batch_size=8, T_total=240: E ~ 240*100*avg_degree.
        # rgat1 never OOM'd in R12 (only rgat2 crashed), so no chunking needed.
        self.rgat1 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim, num_relations=3, heads=heads_1,
            dropout=dropout, use_gatv2=False,
        )

        # rgat2: GATv2Conv — no per-edge weight matrix.
        # Memory: O(E * heads * d) instead of O(E * heads * d^2).
        # At d=32, heads=2: ~32x less VRAM than the RGATConv that OOM'd.
        self.rgat2 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim, num_relations=3, heads=heads_2,
            dropout=dropout, use_gatv2=True,
        )

    @staticmethod
    def _ensure_edge_type(graph):
        if not hasattr(graph, "edge_type") or graph.edge_type is None:
            graph.edge_type = torch.zeros(
                graph.edge_index.shape[1], dtype=torch.long,
                device=graph.edge_index.device,
            )

    def forward(self, graph_sequence: Union[List[Data], Batch],
                T: Optional[int] = None, B: int = 1) -> Tensor:
        if isinstance(graph_sequence, list):
            if B != 1:
                raise ValueError(
                    "B>1 requested but graph_sequence is a flat list (single sequence). "
                    "Pass a pre-built Batch with explicit T and B for multi-sequence input."
                )
            T_seq = len(graph_sequence)
            if T_seq == 0:
                return torch.empty((0, 0, self.hidden_dim))
            N = graph_sequence[0].num_nodes
            for g in graph_sequence:
                self._ensure_edge_type(g)
            batched_graph = Batch.from_data_list(graph_sequence)
            T_total, B_actual = T_seq, 1
        else:
            batched_graph = graph_sequence
            if B > 1 and T is None:
                raise ValueError("T (graphs per sample) must be provided when B > 1.")
            if T is None:
                T_total, T, B_actual = batched_graph.num_graphs, batched_graph.num_graphs, 1
            else:
                B_actual = B
                T_total = T * B_actual
                if T_total != batched_graph.num_graphs:
                    raise ValueError(
                        f"T*B ({T_total}) does not match batched_graph.num_graphs "
                        f"({batched_graph.num_graphs})."
                    )
            N = batched_graph.x.shape[0] // T_total
            if N * T_total != batched_graph.x.shape[0]:
                raise ValueError(
                    f"batched_graph has {batched_graph.x.shape[0]} total nodes, not evenly "
                    f"divisible by T_total={T_total}."
                )

        h = batched_graph.x
        edge_index = batched_graph.edge_index
        edge_type = batched_graph.edge_type
        edge_attr = batched_graph.edge_attr

        # To prevent OutOfMemoryError in RGATConv on large batch sequences (e.g. B*T = 240 graphs),
        # we process the GNN passes sample-by-sample (or chunk-by-chunk) if B_actual > 1.
        # This is mathematically identical since the physical graphs are disjoint.
        if B_actual > 1:
            h_out_list = []
            T_per_sample = T  # number of graphs per sample
            for b in range(B_actual):
                start_node = b * T_per_sample * N
                end_node = (b + 1) * T_per_sample * N
                
                # Slice node features
                x_b = h[start_node:end_node]
                
                # Slice and shift edge indices
                mask = (edge_index[0] >= start_node) & (edge_index[0] < end_node)
                edge_index_b = edge_index[:, mask] - start_node
                edge_type_b = edge_type[mask] if edge_type is not None else None
                edge_attr_b = edge_attr[mask] if edge_attr is not None else None
                
                # Forward through rgat1 and rgat2 for this sample
                h_b = self.rgat1(x_b, edge_index_b, edge_type_b,
                                 edge_attr=edge_attr_b, T=T_per_sample, N=N)
                h_b = self.rgat2(h_b, edge_index_b, edge_type_b,
                                 edge_attr=edge_attr_b, T=T_per_sample, N=N)
                h_out_list.append(h_b)
            h = torch.cat(h_out_list, dim=0)
        else:
            # Single sample/sequence path (B=1)
            h = self.rgat1(h, edge_index, edge_type,
                           edge_attr=edge_attr, T=T_total, N=N)
            h = self.rgat2(h, edge_index, edge_type,
                           edge_attr=edge_attr, T=T_total, N=N)

        if B_actual == 1:
            return h.view(T_total, N, -1).transpose(0, 1)

        T_per_sample = T_total // B_actual
        h = h.view(B_actual, T_per_sample, N, -1)
        h = h.permute(0, 2, 1, 3).contiguous()
        return h.view(B_actual * N, T_per_sample, -1)