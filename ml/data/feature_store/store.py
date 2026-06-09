import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class FeatureStore:
    """Central interface for loading model-ready features from Supabase."""

    def __init__(self) -> None:
        """Initialize with Supabase client using SERVICE_ROLE_KEY from ml/.env"""
        supabase_url: Optional[str] = os.environ.get("SUPABASE_URL")
        supabase_key: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            print("Error: SUPABASE keys must be set in ml/.env")
            sys.exit(1)
            
        self.supabase: Client = create_client(supabase_url, supabase_key)

    def _fetch_all(self, table: str, query: any) -> List[Dict[str, Any]]:
        """Helper to paginate Supabase queries."""
        all_rows = []
        offset = 0
        limit = 1000
        while True:
            res = query.range(offset, offset + limit - 1).execute()
            if not res.data:
                break
            all_rows.extend(res.data)
            if len(res.data) < limit:
                break
            offset += limit
        return all_rows

    def load_node_features(
        self,
        start_date: str,
        end_date: str,
        assets: List[str]
    ) -> Dict[str, pd.DataFrame]:
        """
        Returns dict mapping asset symbol → DataFrame.
        """
        out: Dict[str, pd.DataFrame] = {}
        
        # 1. Load assets
        assets_res = self.supabase.table("assets").select("id, symbol, market_cap_usd").in_("symbol", assets).execute()
        if not assets_res.data:
            return out
            
        asset_map = {row["symbol"]: row["id"] for row in assets_res.data}
        mcap_map = {row["symbol"]: row.get("market_cap_usd", 0) for row in assets_res.data}

        # 2. Load macro indicators (same for all)
        macro_query = (
            self.supabase.table("macro_indicators")
            .select("timestamp, fed_rate, cpi, inflation, vix")
            .gte("timestamp", start_date)
            .lte("timestamp", end_date)
        )
        macro_rows = self._fetch_all("macro_indicators", macro_query)
        macro_df = pd.DataFrame(macro_rows)
        if not macro_df.empty:
            macro_df["timestamp"] = pd.to_datetime(macro_df["timestamp"])
            macro_df = macro_df.set_index("timestamp").sort_index()

        for symbol in assets:
            if symbol not in asset_map:
                continue
            asset_id = asset_map[symbol]
            mcap = mcap_map[symbol]

            # 3. Load OHLCV
            ohlcv_query = (
                self.supabase.table("ohlcv")
                .select("timestamp, open, high, low, close, volume")
                .eq("asset_id", asset_id)
                .gte("timestamp", start_date)
                .lte("timestamp", end_date)
            )
            ohlcv_rows = self._fetch_all("ohlcv", ohlcv_query)
            if not ohlcv_rows:
                continue
            df_ohlcv = pd.DataFrame(ohlcv_rows)
            df_ohlcv["timestamp"] = pd.to_datetime(df_ohlcv["timestamp"])
            df_ohlcv = df_ohlcv.set_index("timestamp").sort_index()
            
            # 4. Load Tech Features
            tech_query = (
                self.supabase.table("technical_features")
                .select("timestamp, rsi_14, macd, macd_signal, atr_14, bb_width, returns_1d, returns_7d, volatility_7d")
                .eq("asset_id", asset_id)
                .gte("timestamp", start_date)
                .lte("timestamp", end_date)
            )
            tech_rows = self._fetch_all("technical_features", tech_query)
            df_tech = pd.DataFrame(tech_rows)
            if not df_tech.empty:
                df_tech["timestamp"] = pd.to_datetime(df_tech["timestamp"])
                df_tech = df_tech.set_index("timestamp").sort_index()
            
            # 5. Load Sentiment
            sent_query = (
                self.supabase.table("sentiment")
                .select("timestamp, sentiment_score, fear_greed_norm, community_score, public_interest")
                .eq("asset_id", asset_id)
                .gte("timestamp", start_date)
                .lte("timestamp", end_date)
            )
            sent_rows = self._fetch_all("sentiment", sent_query)
            df_sent = pd.DataFrame(sent_rows)
            if not df_sent.empty:
                df_sent["timestamp"] = pd.to_datetime(df_sent["timestamp"])
                df_sent = df_sent.set_index("timestamp").sort_index()

            # Merge all DataFrames
            df = df_ohlcv
            if not df_tech.empty:
                df = df.join(df_tech, how="left")
            if not df_sent.empty:
                df = df.join(df_sent, how="left")
            if not macro_df.empty:
                df = df.join(macro_df, how="left")
            
            df["market_cap_usd"] = mcap

            # Ensure proper types
            df = df.astype(float)

            # Forward-fill first, then fill remaining with 0
            df = df.ffill().fillna(0.0)

            # Reorder exactly as requested
            expected_cols = [
                "open", "high", "low", "close", "volume",
                "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
                "returns_1d", "returns_7d", "volatility_7d",
                "sentiment_score", "fear_greed_norm", "community_score",
                "public_interest", "market_cap_usd",
                "fed_rate", "cpi", "inflation", "vix"
            ]
            
            # Add any missing cols with 0
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = 0.0

            df = df[expected_cols]
            df = df.reset_index() # puts timestamp as first column
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
