import torch
import torch.nn as nn
from torch import Tensor
from typing import Optional, List, Union
from torch_geometric.data import Batch, Data
from ml.models.ast_gnn import AdaptiveRelationalGNN


class SpatioTemporalGAT(nn.Module):
    """
    Applies relation-aware GNN to each snapshot independently in one
    vectorized pass.

    Two calling conventions:
      1. LEGACY (single sequence): graph_sequence = List[Data] of length T.
         B is implicitly 1. Returns (N, T, hidden_dim). Unchanged behavior.
      2. BATCHED (NEW): graph_sequence = a pre-built PyG Batch containing
         B*T graphs concatenated SAMPLE-MAJOR (sample0's T graphs in temporal
         order, then sample1's T graphs, ...), with explicit T (per-sample
         window length) and B (number of sequences in this minibatch).
         Returns (B*N, T, hidden_dim) — directly consumable by TemporalTCN's
         (batch, T, hidden) convention with batch=B*N.

    ASSUMPTION (please verify against ast_gnn.py if you have it):
    AdaptiveRelationalGNN is given a single combined T = total snapshot count
    (B*T for the new path). This is safe IF it only uses T to reshape a flat
    (T*N, hidden) tensor into per-snapshot chunks, with no operation assuming
    temporal continuity/adjacency across the WHOLE T axis. Since edges only
    ever connect nodes within a single graph (block-diagonal via
    Batch.from_data_list), spatial convolution itself is unaffected either
    way — only a hypothetical *temporal* operation inside ast_gnn.py would
    break this assumption.
    """

    def __init__(self, hidden_dim: int = 128, heads_1: int = 4, heads_2: int = 2, dropout: float = 0.1):
        super().__init__()
        self.hidden_dim = hidden_dim
        # rgat1: standard RGATConv with temporal chunking (chunk=8 snapshots at a time)
        # to cap peak edge count to 8*N edges instead of B*T*N edges.
        self.rgat1 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim, num_relations=3, heads=heads_1,
            dropout=dropout, rgat_chunk=8,
        )
        # rgat2: switched to GATv2Conv (use_gatv2=True) — eliminates the per-edge
        # weight matrix (w shape: E × heads × d × d) that caused the 2.94 GiB OOM.
        # GATv2 is strictly more expressive than GATv1 at ~32x lower VRAM cost.
        self.rgat2 = AdaptiveRelationalGNN(
            hidden_dim=hidden_dim, num_relations=3, heads=heads_2,
            dropout=dropout, use_gatv2=True, rgat_chunk=8,
        )

    @staticmethod
    def _ensure_edge_type(graph):
        if not hasattr(graph, "edge_type") or graph.edge_type is None:
            graph.edge_type = torch.zeros(
                graph.edge_index.shape[1], dtype=torch.long, device=graph.edge_index.device
            )

    def forward(self, graph_sequence: Union[List[Data], Batch], T: Optional[int] = None, B: int = 1) -> Tensor:
        if isinstance(graph_sequence, list):
            # ---- Legacy path: exactly one sequence, B forced to 1 ----
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
            # ---- Batched path: caller already flattened B*T graphs sample-major ----
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
                    f"batched_graph has {batched_graph.x.shape[0]} total nodes, not evenly divisible "
                    f"by T_total={T_total}. This means graphs in this batch have inconsistent node counts."
        )

        h = batched_graph.x
        h = self.rgat1(h, batched_graph.edge_index, batched_graph.edge_type,
                        edge_attr=batched_graph.edge_attr, T=T_total, N=N)
        h = self.rgat2(h, batched_graph.edge_index, batched_graph.edge_type,
                        edge_attr=batched_graph.edge_attr, T=T_total, N=N)

        if B_actual == 1:
            # (T, N, hidden) -> (N, T, hidden) — unchanged legacy output
            return h.view(T_total, N, -1).transpose(0, 1)

        # (B*T, N, hidden) -> (B, T, N, hidden) -> (B, N, T, hidden) -> (B*N, T, hidden)
        T_per_sample = T_total // B_actual
        h = h.view(B_actual, T_per_sample, N, -1)
        h = h.permute(0, 2, 1, 3).contiguous()
        return h.view(B_actual * N, T_per_sample, -1)