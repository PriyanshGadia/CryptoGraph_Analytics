from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import torch
import torch_geometric.data
from supabase import Client
from typing import Dict, List, Tuple
from ml.graph.edge_types import SECTORS

class DynamicGraphBuilder:
    """Builds dynamic multi-relational graph for a given date."""

    def __init__(self, supabase_client: Client, asset_symbols: List[str]):
        self.client = supabase_client
        self.symbols = asset_symbols
        self.symbol_to_idx = {s: i for i, s in enumerate(asset_symbols)}

    def build_graph(
        self,
        date: datetime,
        features: Dict[str, pd.DataFrame]
    ) -> torch_geometric.data.Data:
        
        # Ensure features are indexed by timestamp and tz-aware
        proc_features = {}
        for sym, df in features.items():
            if not df.empty:
                pdf = df.copy()
                if "timestamp" in pdf.columns:
                    pdf = pdf.set_index("timestamp")
                if pdf.index.tz is None:
                    pdf.index = pdf.index.tz_localize("UTC")
                proc_features[sym] = pdf
                
        # Ensure date is tz-aware
        target_date = pd.to_datetime(date)
        if target_date.tz is None:
            target_date = target_date.tz_localize("UTC")
            
        N = len(self.symbols)
        # Node features
        feature_cols = [
            "open", "high", "low", "close", "volume", 
            "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d", 
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
            "market_cap_usd",
            "fed_rate", "cpi", "inflation", "vix"
        ]
        
        # STEP 1: Node Features
        x_list = []
        for sym in self.symbols:
            if sym in proc_features:
                df = proc_features[sym]
                try:
                    row = df.loc[target_date]
                    vals = row[feature_cols].values.astype(np.float32)
                except KeyError:
                    vals = np.zeros(len(feature_cols), dtype=np.float32)
            else:
                vals = np.zeros(len(feature_cols), dtype=np.float32)
            x_list.append(vals)
            
        x = torch.tensor(np.array(x_list), dtype=torch.float32)

        # Dictionary to accumulate edges: (u, v) -> weight
        edges_dict: Dict[Tuple[int, int], float] = {}

        def add_edge(u: int, v: int, w: float):
            if u == v:
                return
            if (u, v) not in edges_dict or edges_dict[(u, v)] < w:
                edges_dict[(u, v)] = w
            if (v, u) not in edges_dict or edges_dict[(v, u)] < w:
                edges_dict[(v, u)] = w

        # STEP 2: Correlation edges
        start_corr = target_date - timedelta(days=30)
        returns_matrix = []
        for sym in self.symbols:
            if sym in proc_features:
                df = proc_features[sym]
                # last 30 days ending on date
                mask = (df.index > start_corr) & (df.index <= target_date)
                subset = df.loc[mask, "returns_1d"]
                if not subset.empty and len(subset) > 0:
                    returns_matrix.append(subset.values)
                else:
                    returns_matrix.append(np.zeros(30))
            else:
                returns_matrix.append(np.zeros(30))
                
        # pad/truncate to same length if lengths differ
        max_len = max(len(r) for r in returns_matrix) if returns_matrix else 30
        padded = []
        for r in returns_matrix:
            if len(r) < max_len:
                padded.append(np.pad(r, (0, max_len - len(r)), 'constant'))
            elif len(r) > max_len:
                padded.append(r[:max_len])
            else:
                padded.append(r)
                
        if padded:
            corr_mat = np.corrcoef(padded)
            for i in range(N):
                for j in range(i + 1, N):
                    if not np.isnan(corr_mat[i, j]) and abs(corr_mat[i, j]) > 0.6:
                        add_edge(i, j, float(corr_mat[i, j]))

        # STEP 3: Market cap edges
        for i in range(N):
            for j in range(i + 1, N):
                try:
                    mc_i = float(proc_features[self.symbols[i]].loc[target_date, "market_cap_usd"])
                    mc_j = float(proc_features[self.symbols[j]].loc[target_date, "market_cap_usd"])
                    max_mc = max(mc_i, mc_j)
                    weight = min(mc_i, mc_j) / max_mc if max_mc > 0 else 0
                    if weight > 0.3:
                        add_edge(i, j, weight)
                except KeyError:
                    pass

        # STEP 4: Sector edges
        for sector, syms in SECTORS.items():
            valid_idx = [self.symbol_to_idx[s] for s in syms if s in self.symbol_to_idx]
            for i in range(len(valid_idx)):
                for j in range(i + 1, len(valid_idx)):
                    add_edge(valid_idx[i], valid_idx[j], 1.0)

        # STEP 5: Merge edges
        if not edges_dict:
            edge_index = torch.empty((2, 0), dtype=torch.long)
            edge_attr = torch.empty((0, 1), dtype=torch.float32)
        else:
            edge_list = list(edges_dict.items())
            edge_indices = [[u, v] for (u, v), w in edge_list]
            edge_weights = [[w] for (u, v), w in edge_list]
            edge_index = torch.tensor(edge_indices, dtype=torch.long).t().contiguous()
            edge_attr = torch.tensor(edge_weights, dtype=torch.float32)

        return torch_geometric.data.Data(x=x, edge_index=edge_index, edge_attr=edge_attr, num_nodes=N)

    def build_temporal_graph_sequence(
        self,
        start_date: datetime,
        end_date: datetime,
        features: Dict[str, pd.DataFrame],
        lookback_window: int = 30
    ) -> List[torch_geometric.data.Data]:
        
        sequence = []
        current_date = start_date
        while current_date <= end_date:
            missing_count = 0
            for sym in self.symbols:
                if sym not in features or current_date not in features[sym].index:
                    missing_count += 1
            
            if missing_count / len(self.symbols) <= 0.1:
                g = self.build_graph(current_date, features)
                sequence.append(g)
                
            current_date += timedelta(days=1)
            
        return sequence

    def save_graph_snapshot(
        self,
        date: datetime,
        graph: torch_geometric.data.Data,
        asset_symbols: List[str]
    ) -> None:
        if self.client is None:
            return
            
        # Fetch asset IDs
        res = self.client.table("assets").select("id, symbol").in_("symbol", asset_symbols).execute()
        if not res.data:
            return
        symbol_to_id = {row["symbol"]: row["id"] for row in res.data}

        edge_index = graph.edge_index.numpy()
        edge_attr = graph.edge_attr.numpy()

        records = []
        timestamp_str = date.isoformat()
        
        for i in range(edge_index.shape[1]):
            u_sym = asset_symbols[edge_index[0, i]]
            v_sym = asset_symbols[edge_index[1, i]]
            
            if u_sym in symbol_to_id and v_sym in symbol_to_id:
                records.append({
                    "timestamp": timestamp_str,
                    "source_asset": symbol_to_id[u_sym],
                    "target_asset": symbol_to_id[v_sym],
                    "weight": float(edge_attr[i, 0]),
                    "edge_type": "mixed"
                })

        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            try:
                self.client.table("graph_snapshots").upsert(batch).execute()
            except Exception as e:
                print(f"Error upserting graph snapshot: {e}")
