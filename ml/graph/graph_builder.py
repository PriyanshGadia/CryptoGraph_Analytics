from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import torch
import torch_geometric.data
from typing import Any, Dict, List, Optional, Tuple
from ml.graph.edge_types import SECTORS

# supabase is optional — inference/training pipelines pass client=None
try:
    from supabase import Client as _SupabaseClient
except ImportError:
    _SupabaseClient = None  # type: ignore

class DynamicGraphBuilder:
    """Builds dynamic multi-relational graph for a given date.
    
    CRITICAL: This does NOT use a fixed graph structure. The ST-GCN receives
    dynamic graphs recalculated iteratively (e.g. daily/hourly) using 
    rolling 30-day Pearson correlation of returns and dynamic market cap weighting.
    The SpatioTemporalGAT learns the dynamic importance of connections via Attention.
    """

    def __init__(self, supabase_client: Optional[Any], asset_symbols: List[str], feature_dim: int = 24):
        self.client = supabase_client
        self.symbols = asset_symbols
        self.symbol_to_idx = {s: i for i, s in enumerate(asset_symbols)}
        self.feature_dim = feature_dim
        self.rolling_min_cache = {}
        self.rolling_max_cache = {}
        self._cached_len = {}

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
            "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi", "inflation", "vix"
        ]
        if self.feature_dim == 27:
            feature_cols.extend(["tvl", "revenue", "active_users"])
        
        # STEP 1: Node Features with Rolling 30-day Z-Score normalization (all features)
        x_list = []
        for sym in self.symbols:
            if sym in proc_features:
                df = proc_features[sym]
                # Cache rolling mean/std for ALL feature columns (not just 6)
                if sym not in self.rolling_min_cache or len(df) != self._cached_len.get(sym, -1):
                    cols_present = [c for c in feature_cols if c in df.columns]
                    # Store rolling mean in min_cache, rolling std in max_cache (reusing cache names)
                    self.rolling_min_cache[sym] = df[cols_present].rolling(window=30, min_periods=1).mean()
                    rolling_std = df[cols_present].rolling(window=30, min_periods=1).std()
                    # Replace zero std with 1.0 to avoid division by zero
                    self.rolling_max_cache[sym] = rolling_std.replace(0.0, 1.0).fillna(1.0)
                    self._cached_len[sym] = len(df)
                
                df_mean = self.rolling_min_cache[sym]
                df_std = self.rolling_max_cache[sym]
                try:
                    row = df.loc[target_date]
                    row_mean = df_mean.loc[target_date]
                    row_std = df_std.loc[target_date]
                    vals = []
                    for col in feature_cols:
                        val = row[col] if not pd.isna(row[col]) else 0.0
                        if col in row_mean.index:
                            col_mean = row_mean[col] if not pd.isna(row_mean[col]) else 0.0
                            col_std = row_std[col] if not pd.isna(row_std[col]) else 1.0
                            if col_std == 0.0:
                                col_std = 1.0
                            val = (float(val) - col_mean) / col_std
                        # Clip to [-5, 5] to handle outliers
                        val = max(-5.0, min(5.0, float(val)))
                        vals.append(val)
                    vals = np.array(vals, dtype=np.float32)
                except Exception:
                    vals = np.zeros(len(feature_cols), dtype=np.float32)
            else:
                vals = np.zeros(len(feature_cols), dtype=np.float32)
            x_list.append(vals)
            
        x = torch.tensor(np.array(x_list), dtype=torch.float32)
        # Dictionary to accumulate edges: (u, v, relation_type) -> weight
        edges_dict: Dict[Tuple[int, int, int], float] = {}

        def add_edge(u: int, v: int, w: float, rel: int):
            if u == v:
                return
            edges_dict[(u, v, rel)] = w
            edges_dict[(v, u, rel)] = w

        # STEP 2: Correlation edges (Relation 2)
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
            # Handle constant/zero returns safely to avoid division-by-zero warnings in np.corrcoef
            padded_arr = np.array(padded)
            std = np.std(padded_arr, axis=1)
            zero_std_idx = np.where(std == 0.0)[0]
            if len(zero_std_idx) > 0:
                padded_arr[zero_std_idx, :] = padded_arr[zero_std_idx, :] + np.random.normal(0, 1e-9, padded_arr[zero_std_idx, :].shape)
            
            corr_mat = np.corrcoef(padded_arr)
            corr_mat = np.nan_to_num(corr_mat, nan=0.0, posinf=0.0, neginf=0.0)
            
            # Vectorized thresholding for 20k scaling
            row_idx, col_idx = np.where(np.abs(corr_mat) > 0.6)
            for i, j in zip(row_idx, col_idx):
                if i < j:
                    add_edge(int(i), int(j), float(corr_mat[i, j]), 2)

        # STEP 3: Market cap edges (Relation 1)
        market_caps = {}
        for idx, sym in enumerate(self.symbols):
            if sym in proc_features:
                try:
                    val = proc_features[sym].loc[target_date, "market_cap_usd"]
                    market_caps[idx] = float(val) if not pd.isna(val) else 0.0
                except KeyError:
                    market_caps[idx] = 0.0
            else:
                market_caps[idx] = 0.0

        for i in range(N):
            mc_i = market_caps[i]
            if mc_i <= 0:
                continue
            for j in range(i + 1, N):
                mc_j = market_caps[j]
                if mc_j <= 0:
                    continue
                max_mc = max(mc_i, mc_j)
                weight = min(mc_i, mc_j) / max_mc
                if weight > 0.3:
                    add_edge(i, j, weight, 1)

        # STEP 4: Sector edges (Relation 0)
        for sector, syms in SECTORS.items():
            valid_idx = [self.symbol_to_idx[s] for s in syms if s in self.symbol_to_idx]
            for i in range(len(valid_idx)):
                for j in range(i + 1, len(valid_idx)):
                    add_edge(valid_idx[i], valid_idx[j], 1.0, 0)

        # STEP 5: Merge edges
        if not edges_dict:
            edge_index = torch.empty((2, 0), dtype=torch.long)
            edge_attr = torch.empty((0, 1), dtype=torch.float32)
            edge_type = torch.empty((0,), dtype=torch.long)
        else:
            edge_list = list(edges_dict.items())
            edge_indices = [[u, v] for (u, v, rel), w in edge_list]
            edge_weights = [[w] for (u, v, rel), w in edge_list]
            edge_types = [rel for (u, v, rel), w in edge_list]
            edge_index = torch.tensor(edge_indices, dtype=torch.long).t().contiguous()
            edge_attr = torch.tensor(edge_weights, dtype=torch.float32)
            edge_type = torch.tensor(edge_types, dtype=torch.long)

        return torch_geometric.data.Data(x=x, edge_index=edge_index, edge_attr=edge_attr, edge_type=edge_type, num_nodes=N)

    def build_realtime_graph(
        self,
        features: Dict[str, pd.DataFrame]
    ) -> torch_geometric.data.Data:
        """Constructs an instantaneous snapshot using the latest row of the provided dataframes."""
        N = len(self.symbols)
        feature_cols = [
            "open", "high", "low", "close", "volume", 
            "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d", 
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
            "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi", "inflation", "vix"
        ]
        if self.feature_dim == 27:
            feature_cols.extend(["tvl", "revenue", "active_users"])
            
        # STEP 1: Node Features with Rolling 30-day Z-Score normalization (all features)
        x_list = []
        for sym in self.symbols:
            if sym in features and not features[sym].empty:
                df = features[sym]
                
                if sym not in self.rolling_min_cache or len(df) != self._cached_len.get(sym, -1):
                    cols_present = [c for c in feature_cols if c in df.columns]
                    self.rolling_min_cache[sym] = df[cols_present].rolling(window=30, min_periods=1).mean()
                    rolling_std = df[cols_present].rolling(window=30, min_periods=1).std()
                    self.rolling_max_cache[sym] = rolling_std.replace(0.0, 1.0).fillna(1.0)
                    self._cached_len[sym] = len(df)
                    
                df_mean = self.rolling_min_cache[sym]
                df_std = self.rolling_max_cache[sym]
                try:
                    row = df.iloc[-1]
                    row_mean = df_mean.iloc[-1]
                    row_std = df_std.iloc[-1]
                    vals = []
                    for col in feature_cols:
                        val = row[col] if not pd.isna(row[col]) else 0.0
                        if col in row_mean.index:
                            col_mean = row_mean[col] if not pd.isna(row_mean[col]) else 0.0
                            col_std = row_std[col] if not pd.isna(row_std[col]) else 1.0
                            if col_std == 0.0:
                                col_std = 1.0
                            val = (float(val) - col_mean) / col_std
                        # Clip to [-5, 5] to handle outliers
                        val = max(-5.0, min(5.0, float(val)))
                        vals.append(val)
                    vals = np.array(vals, dtype=np.float32)
                except Exception:
                    vals = np.zeros(len(feature_cols), dtype=np.float32)
            else:
                vals = np.zeros(len(feature_cols), dtype=np.float32)
            x_list.append(vals)
            
        x = torch.tensor(np.array(x_list), dtype=torch.float32)

        # Dictionary to accumulate edges: (u, v, relation_type) -> weight
        edges_dict: Dict[Tuple[int, int, int], float] = {}

        def add_edge(u: int, v: int, w: float, rel: int):
            if u == v: return
            edges_dict[(u, v, rel)] = w
            edges_dict[(v, u, rel)] = w

        # STEP 2: Correlation edges (Relation 2)
        returns_matrix = []
        for sym in self.symbols:
            if sym in features and not features[sym].empty:
                df = features[sym]
                subset = df["close"].pct_change().fillna(0).values
                returns_matrix.append(subset)
            else:
                returns_matrix.append(np.zeros(60))
                
        max_len = max(len(r) for r in returns_matrix) if returns_matrix else 60
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
            # Vectorized thresholding for 20k scaling
            row_idx, col_idx = np.where(np.abs(corr_mat) > 0.6)
            for i, j in zip(row_idx, col_idx):
                if i < j:
                    add_edge(int(i), int(j), float(corr_mat[i, j]), 2)

        # STEP 3: Market cap edges (Relation 1)
        for i in range(N):
            for j in range(i + 1, N):
                try:
                    if self.symbols[i] in features and self.symbols[j] in features:
                        mc_i = float(features[self.symbols[i]].iloc[-1]["market_cap_usd"])
                        mc_j = float(features[self.symbols[j]].iloc[-1]["market_cap_usd"])
                        max_mc = max(mc_i, mc_j)
                        weight = min(mc_i, mc_j) / max_mc if max_mc > 0 else 0
                        if weight > 0.3:
                            add_edge(i, j, weight, 1)
                except KeyError:
                    pass

        # STEP 4: Sector edges (Relation 0)
        for sector, syms in SECTORS.items():
            valid_idx = [self.symbol_to_idx[s] for s in syms if s in self.symbol_to_idx]
            for i in range(len(valid_idx)):
                for j in range(i + 1, len(valid_idx)):
                    add_edge(valid_idx[i], valid_idx[j], 1.0, 0)

        # STEP 5: Merge edges
        if not edges_dict:
            edge_index = torch.empty((2, 0), dtype=torch.long)
            edge_attr = torch.empty((0, 1), dtype=torch.float32)
            edge_type = torch.empty((0,), dtype=torch.long)
        else:
            edge_list = list(edges_dict.items())
            edge_indices = [[u, v] for (u, v, rel), w in edge_list]
            edge_weights = [[w] for (u, v, rel), w in edge_list]
            edge_types = [rel for (u, v, rel), w in edge_list]
            edge_index = torch.tensor(edge_indices, dtype=torch.long).t().contiguous()
            edge_attr = torch.tensor(edge_weights, dtype=torch.float32)
            edge_type = torch.tensor(edge_types, dtype=torch.long)

        return torch_geometric.data.Data(x=x, edge_index=edge_index, edge_attr=edge_attr, edge_type=edge_type, num_nodes=N)

    def build_temporal_graph_sequence(
        self,
        start_date: datetime,
        end_date: datetime,
        features: Dict[str, pd.DataFrame],
        lookback_window: int = 30
    ) -> List[torch_geometric.data.Data]:
        
        sequence = []
        current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_normalized = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Normalize all feature indexes to daily dates for easy lookup
        daily_features = {}
        for sym, df in features.items():
            if not df.empty:
                pdf = df.copy()
                pdf.index = pdf.index.floor('D')
                # drop duplicates if any (e.g. multiple entries per day)
                pdf = pdf[~pdf.index.duplicated(keep='last')]
                daily_features[sym] = pdf

        while current_date <= end_date_normalized:
            missing_count = 0
            for sym in self.symbols:
                if sym not in daily_features or current_date not in daily_features[sym].index:
                    missing_count += 1
            
            if missing_count / len(self.symbols) <= 0.1:
                g = self.build_graph(current_date, daily_features)
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
