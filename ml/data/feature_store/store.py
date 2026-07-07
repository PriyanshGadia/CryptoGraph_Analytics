import sqlite3
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

# Resolve the local SQLite database path.
_DB_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent.parent / "backend" / "cryptograph.db",
    Path(__file__).resolve().parent.parent.parent.parent / "cryptograph.db",
]
DB_PATH: Optional[Path] = next((p for p in _DB_CANDIDATES if p.exists()), _DB_CANDIDATES[0])

class FeatureStore:
    """Central interface for loading model-ready features from SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize with a path to the local SQLite database."""
        self.db_path = str(db_path or DB_PATH)

    def _conn(self) -> sqlite3.Connection:
        """Return a new SQLite connection with dict-row factory."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load_node_features(
        self,
        start_date: str,
        end_date: str,
        assets: List[str],
        expected_features: int = 24
    ) -> Dict[str, pd.DataFrame]:
        """
        Returns dict mapping asset symbol → DataFrame with exactly `expected_features`
        feature columns matching STGCNModel(in_features=expected_features).

        Uses batched SQL queries — one per table — to avoid N+1.
        """
        conn = self._conn()
        out: Dict[str, pd.DataFrame] = {}

        try:
            # ----- 1. Load assets (batched) -----
            placeholders = ",".join("?" for _ in assets)
            asset_rows = conn.execute(
                f"SELECT id, symbol, market_cap_usd FROM assets WHERE symbol IN ({placeholders})",
                assets,
            ).fetchall()
            if not asset_rows:
                return out

            asset_map = {r["symbol"]: r["id"] for r in asset_rows}
            mcap_map = {r["symbol"]: (r["market_cap_usd"] or 0) for r in asset_rows}
            asset_ids = list(asset_map.values())
            id_ph = ",".join("?" for _ in asset_ids)

            # ----- 2. Macro indicators (global, one query) -----
            try:
                macro_rows = conn.execute(
                    "SELECT timestamp, fed_rate, cpi, inflation, vix "
                    "FROM macro_indicators WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
                    (start_date, end_date),
                ).fetchall()
                macro_df = pd.DataFrame([dict(r) for r in macro_rows])
                if not macro_df.empty:
                    macro_df["timestamp"] = pd.to_datetime(macro_df["timestamp"], format='mixed', utc=True)
                    macro_df = macro_df.set_index("timestamp").sort_index()
            except sqlite3.OperationalError:
                macro_df = pd.DataFrame()

            # ----- 3. OHLCV (batched) -----
            ohlcv_rows = conn.execute(
                f"SELECT asset_id, timestamp, open, high, low, close, volume "
                f"FROM ohlcv WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                f"ORDER BY timestamp",
                (*asset_ids, start_date, end_date),
            ).fetchall()
            ohlcv_df = pd.DataFrame([dict(r) for r in ohlcv_rows])

            # ----- 4. Technical features (batched) -----
            try:
                tech_rows = conn.execute(
                    f"SELECT asset_id, timestamp, rsi_14, macd, macd_signal, atr_14, "
                    f"bb_width, returns_1d, returns_7d, volatility_7d "
                    f"FROM technical_features WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                tech_df = pd.DataFrame([dict(r) for r in tech_rows])
            except sqlite3.OperationalError:
                tech_df = pd.DataFrame()

            # ----- 5. Sentiment (batched, now includes the two missing cols) -----
            try:
                sent_rows = conn.execute(
                    f"SELECT asset_id, timestamp, sentiment_score, fear_greed_norm, "
                    f"community_score, public_interest, sentiment_rolling_3d, sentiment_momentum "
                    f"FROM sentiment WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                sent_df = pd.DataFrame([dict(r) for r in sent_rows])
            except sqlite3.OperationalError:
                sent_df = pd.DataFrame()

            # ----- 5.5. On-Chain Metrics (batched) -----
            try:
                onchain_rows = conn.execute(
                    f"SELECT asset_id, timestamp, tvl, revenue, active_users "
                    f"FROM onchain_metrics WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                onchain_df = pd.DataFrame([dict(r) for r in onchain_rows])
            except sqlite3.OperationalError:
                onchain_df = pd.DataFrame()

        finally:
            conn.close()

        # ----- 6. Assemble per-asset DataFrames -----
        for symbol in assets:
            if symbol not in asset_map:
                continue
            asset_id = asset_map[symbol]
            mcap = mcap_map[symbol]

            # Filter per-asset from batched frames
            if ohlcv_df.empty:
                continue
            df_ohlcv = ohlcv_df[ohlcv_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
            if df_ohlcv.empty:
                continue
            df_ohlcv["timestamp"] = pd.to_datetime(df_ohlcv["timestamp"], format='mixed', utc=True)
            df_ohlcv = df_ohlcv.set_index("timestamp").sort_index()

            df_tech = pd.DataFrame()
            if not tech_df.empty:
                df_tech = tech_df[tech_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_tech.empty:
                    df_tech["timestamp"] = pd.to_datetime(df_tech["timestamp"], format='mixed', utc=True)
                    df_tech = df_tech.set_index("timestamp").sort_index()

            df_sent = pd.DataFrame()
            if not sent_df.empty:
                df_sent = sent_df[sent_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_sent.empty:
                    df_sent["timestamp"] = pd.to_datetime(df_sent["timestamp"], format='mixed', utc=True)
                    df_sent = df_sent.set_index("timestamp").sort_index()

            df_onchain = pd.DataFrame()
            if not onchain_df.empty:
                df_onchain = onchain_df[onchain_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_onchain.empty:
                    df_onchain["timestamp"] = pd.to_datetime(df_onchain["timestamp"], format='mixed', utc=True)
                    df_onchain = df_onchain.set_index("timestamp").sort_index()

            # Merge
            df = df_ohlcv
            if not df_tech.empty:
                df = df.join(df_tech, how="left")
            if not df_sent.empty:
                df = df.join(df_sent, how="left")
            if not df_onchain.empty:
                df = df.join(df_onchain, how="left")
            if not macro_df.empty:
                df = df.join(macro_df, how="left")

            df["market_cap_usd"] = mcap
            df = df.astype(float)
            
            # Standard neutral values to avoid artificial signal leakage
            fill_values = {
                "rsi_14": 50.0,
                "fear_greed_norm": 0.5,
                "sentiment_score": 0.0,
                "sentiment_rolling_3d": 0.0,
                "sentiment_momentum": 0.0,
                "fed_rate": 5.25,
                "cpi": 3.0,
                "inflation": 2.5,
                "vix": 15.0,
                "returns_1d": 0.0,
                "returns_7d": 0.0,
                "volatility_7d": 0.0
            }
            df = df.interpolate(method='linear', limit_direction='both').fillna(0.0)
            
            for col, val in fill_values.items():
                if col in df.columns:
                    df[col] = df[col].fillna(val)

            expected_cols = [
                "open", "high", "low", "close", "volume",
                "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
                "returns_1d", "returns_7d", "volatility_7d",
                "sentiment_score", "fear_greed_norm", "community_score",
                "public_interest", "sentiment_rolling_3d", "sentiment_momentum",
                "market_cap_usd",
                "fed_rate", "cpi", "inflation", "vix"
            ]
            if expected_features == 27:
                expected_cols.extend(["tvl", "revenue", "active_users"])

            for col in expected_cols:
                if col not in df.columns:
                    df[col] = 0.0

            df = df[expected_cols]
            df = df.reset_index()  # puts timestamp as first column
            out[symbol] = df

        return out

    def validate_features(self, features: Dict[str, pd.DataFrame]) -> bool:
        """Validates feature DataFrames."""
        if not features:
            raise ValueError("No features provided.")

        date_ranges = {}

        for symbol, df in features.items():
            if df.empty:
                raise ValueError(f"DataFrame for {symbol} is empty.")
            
            # Check for NaN or Inf
            num_cols = df.select_dtypes(include=[np.number])
            if num_cols.isna().sum().sum() > 0:
                raise ValueError(f"NaN values found in {symbol}")
            if np.isinf(num_cols).sum().sum() > 0:
                raise ValueError(f"Inf values found in {symbol}")
                
            # Bounds checks
            if "rsi_14" in df.columns:
                rsi = df["rsi_14"]
                if (rsi < 0).any() or (rsi > 100).any():
                    raise ValueError(f"RSI out of bounds [0, 100] for {symbol}")
            
            if "sentiment_score" in df.columns:
                sent = df["sentiment_score"]
                if (sent < -1.0).any() or (sent > 1.0).any():
                    raise ValueError(f"Sentiment score out of bounds [-1, 1] for {symbol}")
                    
            if "fear_greed_norm" in df.columns:
                fg = df["fear_greed_norm"]
                if (fg < 0.0).any() or (fg > 1.0).any():
                    raise ValueError(f"Fear Greed Norm out of bounds [0, 1] for {symbol}")

            # Store date range
            date_ranges[symbol] = (df["timestamp"].min(), df["timestamp"].max())

        # Check date matching
        first_symbol = list(date_ranges.keys())[0]
        ref_range = date_ranges[first_symbol]
        for symbol, rng in date_ranges.items():
            if rng != ref_range:
                warnings.warn(f"Date range mismatch: {symbol} has {rng} vs {first_symbol} has {ref_range}")

        return True

    def get_target_labels(self, features: Dict[str, pd.DataFrame], horizon_days: int = 1) -> Dict[str, pd.Series]:
        """Compute classification labels for each asset."""
        labels = {}
        for symbol, df in features.items():
            if "close" not in df.columns:
                continue

            forward_return = (df["close"].shift(-horizon_days) - df["close"]) / df["close"]
            
            def classify(ret: float) -> str:
                if pd.isna(ret):
                    return "neutral"
                if ret > 0.03:
                    return "strong_up"
                elif 0.00 < ret <= 0.03:
                    return "up"
                elif -0.01 < ret <= 0.00:
                    return "neutral"
                elif -0.03 < ret <= -0.01:
                    return "down"
                else:
                    return "strong_down"
            
            lbls = forward_return.apply(classify)
            # Drop last horizon_days rows
            lbls = lbls.iloc[:-horizon_days]
            lbls.index = df.index[:-horizon_days]
            labels[symbol] = lbls
            
        return labels
