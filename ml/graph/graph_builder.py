from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import torch
import torch_geometric.data
from typing import Any, Dict, List, Optional, Tuple
from ml.graph.edge_types import SECTORS


def _compute_momentum_features(df: pd.DataFrame, target_date: pd.Timestamp) -> Dict[str, float]:
    """
    Compute 5 engineered momentum features from OHLCV data.
    All features are computable from yfinance OHLCV data (no external APIs needed).

    Replaces the 5 dead/near-zero yfinance features:
      macd_signal (noisy derivative), sentiment_rolling_3d (zero), inflation (constant),
      vix (constant), low (highly correlated with close).

    Returns a dict with keys: momentum_5d, volume_surge, intraday_range,
      price_acceleration, rsi_divergence.
    """
    result = {
        "momentum_5d": 0.0,
        "volume_surge": 0.0,
        "intraday_range": 0.0,
        "price_acceleration": 0.0,
        "rsi_divergence": 0.0,
    }
    try:
        # Select data up to and including target_date
        hist = df[df.index <= target_date].tail(25)  # at most 25 rows
        if len(hist) < 2:
            return result

        close = hist["close"].values.astype(np.float64)
        volume = hist["volume"].values.astype(np.float64) if "volume" in hist.columns else None
        high = hist["high"].values.astype(np.float64) if "high" in hist.columns else None
        low_col = hist["low"].values.astype(np.float64) if "low" in hist.columns else None

        # 1. momentum_5d: 5-day price return (short-term momentum)
        if len(close) >= 5:
            mom5 = (close[-1] - close[-5]) / (abs(close[-5]) + 1e-8)
            result["momentum_5d"] = float(np.clip(mom5, -1.0, 1.0))

        # 2. volume_surge: current volume / 21-day average volume (breakout indicator)
        if volume is not None and len(volume) >= 5:
            vol_ma = np.mean(volume[:-1])  # exclude today in MA
            if vol_ma > 1e-8:
                surge = volume[-1] / vol_ma
                result["volume_surge"] = float(np.clip(surge - 1.0, -2.0, 4.0))  # centered at 0

        # 3. intraday_range: (high - low) / close — normalized daily volatility proxy
        if high is not None and low_col is not None and len(close) >= 1:
            rng = (high[-1] - low_col[-1]) / (abs(close[-1]) + 1e-8)
            result["intraday_range"] = float(np.clip(rng, 0.0, 0.5))

        # 4. price_acceleration: short-term momentum minus medium-term momentum
        #    Positive = accelerating up, Negative = decelerating / mean reverting
        if len(close) >= 15:
            mom5_val = (close[-1] - close[-5]) / (abs(close[-5]) + 1e-8)
            mom15_val = (close[-1] - close[-15]) / (abs(close[-15]) + 1e-8)
            accel = mom5_val - mom15_val
            result["price_acceleration"] = float(np.clip(accel, -0.5, 0.5))

        # 5. rsi_divergence: (RSI - 50) / 50, normalized to [-1, 1]
        #    Uses existing rsi_14 if present, else computes manually
        if "rsi_14" in hist.columns:
            rsi_val = float(hist["rsi_14"].iloc[-1])
            if not np.isnan(rsi_val):
                result["rsi_divergence"] = float(np.clip((rsi_val - 50.0) / 50.0, -1.0, 1.0))
        elif len(close) >= 15:
            # Compute RSI manually from close prices
            deltas = np.diff(close[-15:])
            gains = np.where(deltas > 0, deltas, 0.0)
            losses = np.where(deltas < 0, -deltas, 0.0)
            avg_gain = np.mean(gains) + 1e-8
            avg_loss = np.mean(losses) + 1e-8
            rs = avg_gain / avg_loss
            rsi_manual = 100.0 - 100.0 / (1.0 + rs)
            result["rsi_divergence"] = float(np.clip((rsi_manual - 50.0) / 50.0, -1.0, 1.0))
    except Exception:
        pass
    return result

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

    def __init__(self, supabase_client: Optional[Any], asset_symbols: List[str], feature_dim: int = 24, corr_threshold: float = 0.6, mc_threshold: float = 0.3):
        self.client = supabase_client
        self.symbols = asset_symbols
        self.symbol_to_idx = {s: i for i, s in enumerate(asset_symbols)}
        self.feature_dim = feature_dim
        self.corr_threshold = corr_threshold
        self.mc_threshold = mc_threshold
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
        # Feature columns: 24 features.
        # Dead/constant yfinance features (macd_signal, sentiment_rolling_3d, inflation, vix, low)
        # are replaced with 5 engineered OHLCV momentum features:
        #   momentum_5d, volume_surge, intraday_range, price_acceleration, rsi_divergence
        base_feature_cols = [
            "open", "high", "close", "volume",
            "rsi_14", "macd", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d",
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest",
            "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi",
        ]
        engineered_feature_cols = [
            "momentum_5d", "volume_surge", "intraday_range", "price_acceleration", "rsi_divergence"
        ]
        feature_cols = base_feature_cols + engineered_feature_cols
        if self.feature_dim == 27:
            feature_cols.extend(["tvl", "revenue", "active_users"])
        
        # STEP 1: Node Features with Rolling 30-day Z-Score normalization (all features)
        x_list = []
        for sym in self.symbols:
            if sym in proc_features:
                df = proc_features[sym]
                # Cache rolling mean/std for base feature columns only
                if sym not in self.rolling_min_cache or len(df) != self._cached_len.get(sym, -1):
                    cols_present = [c for c in base_feature_cols if c in df.columns]
                    self.rolling_min_cache[sym] = df[cols_present].rolling(window=30, min_periods=1).mean()
                    rolling_std = df[cols_present].rolling(window=30, min_periods=1).std()
                    self.rolling_max_cache[sym] = rolling_std.replace(0.0, 1.0).fillna(1.0)
                    self._cached_len[sym] = len(df)

                df_mean = self.rolling_min_cache[sym]
                df_std = self.rolling_max_cache[sym]
                try:
                    row = df.loc[target_date]
                    row_mean = df_mean.loc[target_date]
                    row_std = df_std.loc[target_date]
                    vals = []
                    # Base features: z-score normalized
                    for col in base_feature_cols:
                        val = row[col] if col in row.index and not pd.isna(row[col]) else 0.0
                        if col in row_mean.index:
                            col_mean = row_mean[col] if not pd.isna(row_mean[col]) else 0.0
                            col_std = row_std[col] if not pd.isna(row_std[col]) else 1.0
                            if col_std == 0.0:
                                col_std = 1.0
                            val = (float(val) - col_mean) / col_std
                        val = max(-5.0, min(5.0, float(val)))
                        vals.append(val)
                    # Engineered features: already bounded, append directly
                    eng = _compute_momentum_features(df, target_date)
                    for col in engineered_feature_cols:
                        vals.append(eng[col])
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
            
            # Keep only top-5 correlated peers per asset to limit density
            K = 5
            for i in range(N):
                corrs = np.abs(corr_mat[i])
                top_indices = np.argsort(corrs)[::-1]
                count = 0
                for j in top_indices:
                    if j == i:
                        continue
                    if corrs[j] > self.corr_threshold:
                        add_edge(i, j, float(corr_mat[i, j]), 2)
                        count += 1
                        if count >= K:
                            break

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

        # Sort indices by market cap and connect to adjacent neighbors in ranking
        valid_mc = [(idx, val) for idx, val in market_caps.items() if val > 0]
        valid_mc.sort(key=lambda x: x[1], reverse=True)
        for rank_idx in range(len(valid_mc)):
            i, mc_i = valid_mc[rank_idx]
            for offset in range(1, 4):  # Connect to top 3 adjacent peers
                if rank_idx + offset < len(valid_mc):
                    j, mc_j = valid_mc[rank_idx + offset]
                    max_mc = max(mc_i, mc_j)
                    weight = min(mc_i, mc_j) / max_mc if max_mc > 0 else 0
                    if weight > self.mc_threshold:
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
        base_feature_cols = [
            "open", "high", "close", "volume",
            "rsi_14", "macd", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d",
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest",
            "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi",
        ]
        engineered_feature_cols = [
            "momentum_5d", "volume_surge", "intraday_range", "price_acceleration", "rsi_divergence"
        ]
        feature_cols = base_feature_cols + engineered_feature_cols
        if self.feature_dim == 27:
            feature_cols.extend(["tvl", "revenue", "active_users"])
            
        # STEP 1: Node Features with Rolling 30-day Z-Score normalization (all features)
        x_list = []
        for sym in self.symbols:
            if sym in features and not features[sym].empty:
                df = features[sym]

                if sym not in self.rolling_min_cache or len(df) != self._cached_len.get(sym, -1):
                    cols_present = [c for c in base_feature_cols if c in df.columns]
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
                    # Use current index timestamp for engineered features
                    target_ts = pd.Timestamp(df.index[-1])
                    vals = []
                    for col in base_feature_cols:
                        val = row[col] if col in row.index and not pd.isna(row[col]) else 0.0
                        if col in row_mean.index:
                            col_mean = row_mean[col] if not pd.isna(row_mean[col]) else 0.0
                            col_std = row_std[col] if not pd.isna(row_std[col]) else 1.0
                            if col_std == 0.0:
                                col_std = 1.0
                            val = (float(val) - col_mean) / col_std
                        val = max(-5.0, min(5.0, float(val)))
                        vals.append(val)
                    eng = _compute_momentum_features(df, target_ts)
                    for col in engineered_feature_cols:
                        vals.append(eng[col])
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
            corr_mat = np.nan_to_num(corr_mat, nan=0.0, posinf=0.0, neginf=0.0)
            
            # Keep only top-5 correlated peers per asset to limit density
            K = 5
            for i in range(N):
                corrs = np.abs(corr_mat[i])
                top_indices = np.argsort(corrs)[::-1]
                count = 0
                for j in top_indices:
                    if j == i:
                        continue
                    if corrs[j] > self.corr_threshold:
                        add_edge(i, j, float(corr_mat[i, j]), 2)
                        count += 1
                        if count >= K:
                            break

        # STEP 3: Market cap edges (Relation 1)
        market_caps = {}
        for idx, sym in enumerate(self.symbols):
            if sym in features and not features[sym].empty:
                try:
                    val = features[sym].iloc[-1]["market_cap_usd"]
                    market_caps[idx] = float(val) if not pd.isna(val) else 0.0
                except (KeyError, IndexError):
                    market_caps[idx] = 0.0
            else:
                market_caps[idx] = 0.0

        # Sort indices by market cap and connect to adjacent neighbors in ranking
        valid_mc = [(idx, val) for idx, val in market_caps.items() if val > 0]
        valid_mc.sort(key=lambda x: x[1], reverse=True)
        for rank_idx in range(len(valid_mc)):
            i, mc_i = valid_mc[rank_idx]
            for offset in range(1, 4):  # Connect to top 3 adjacent peers
                if rank_idx + offset < len(valid_mc):
                    j, mc_j = valid_mc[rank_idx + offset]
                    max_mc = max(mc_i, mc_j)
                    weight = min(mc_i, mc_j) / max_mc if max_mc > 0 else 0
                    if weight > self.mc_threshold:
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
