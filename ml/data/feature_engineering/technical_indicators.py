import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pandas_ta as ta  # noqa: F401
from dotenv import load_dotenv
from supabase import Client, create_client

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in ml/.env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_assets() -> List[Dict[str, Any]]:
    res = supabase.table("assets").select("id, symbol").execute()
    return res.data

def main() -> None:
    assets = get_assets()
    if not assets:
        print("No assets found in database.")
        return

    for asset in assets:
        asset_id = asset["id"]
        symbol = asset["symbol"]

        # Fetch all OHLCV for this asset ordered by timestamp ASC
        # Note: supabase select has a default limit of 1000. We might need pagination if > 1000.
        # OHLCV has millions of rows according to previous logs, so pagination is essential.
        all_rows: List[Dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            res = (
                supabase.table("ohlcv")
                .select("timestamp, open, high, low, close, volume")
                .eq("asset_id", asset_id)
                .order("timestamp", desc=False)
                .range(offset, offset + limit - 1)
                .execute()
            )
            
            if not res.data:
                break
                
            all_rows.extend(res.data)
            
            if len(res.data) < limit:
                break
                
            offset += limit

        if not all_rows:
            continue

        df = pd.DataFrame(all_rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        
        # Ensure numerical types
        cols_to_numeric = ["open", "high", "low", "close", "volume"]
        df[cols_to_numeric] = df[cols_to_numeric].apply(pd.to_numeric)

        # Compute pandas-ta indicators
        df["rsi_14"] = df.ta.rsi(length=14)
        
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df["macd"] = macd["MACD_12_26_9"]
            df["macd_signal"] = macd["MACDs_12_26_9"]
        else:
            df["macd"] = np.nan
            df["macd_signal"] = np.nan
            
        df["atr_14"] = df.ta.atr(length=14)
        
        bb = df.ta.bbands(length=20, std=2)
        if bb is not None and not bb.empty:
            bbu = bb["BBU_20_2.0_2.0"]
            bbl = bb["BBL_20_2.0_2.0"]
            bbm = bb["BBM_20_2.0_2.0"]
            df["bb_width"] = (bbu - bbl) / bbm
        else:
            df["bb_width"] = np.nan

        # Compute manual indicators
        df["returns_1d"] = np.log(df["close"] / df["close"].shift(1))
        df["returns_7d"] = (df["close"] - df["close"].shift(7)) / df["close"].shift(7)
        df["volatility_7d"] = df["returns_1d"].rolling(7).std()

        # Drop rows where any column is NaN (indicator warm-up)
        df = df.dropna()

        if df.empty:
            print(f"Computed features for {symbol}: 0 rows (after dropping NaNs)")
            continue

        # Prepare records for upsert
        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            records.append({
                "asset_id": asset_id,
                "timestamp": row["timestamp"].isoformat(),
                "rsi_14": row["rsi_14"],
                "macd": row["macd"],
                "macd_signal": row["macd_signal"],
                "atr_14": row["atr_14"],
                "bb_width": row["bb_width"],
                "returns_1d": row["returns_1d"],
                "returns_7d": row["returns_7d"],
                "volatility_7d": row["volatility_7d"]
            })

        # Batch upsert
        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            try:
                supabase.table("technical_features").upsert(batch, on_conflict="asset_id,timestamp").execute()
            except Exception as e:
                print(f"Error upserting technical features for {symbol}: {e}")

        print(f"Computed features for {symbol}: {len(records)} rows")

    print("✅ Technical indicators complete")

if __name__ == "__main__":
    main()
