import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE keys must be set in ml/.env")
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

        # Fetch all sentiment rows for this asset ordered by timestamp ASC
        all_rows: List[Dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            res = (
                supabase.table("sentiment")
                .select("timestamp, sentiment_score, fear_greed")
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
        
        df["sentiment_score"] = pd.to_numeric(df["sentiment_score"])
        df["fear_greed"] = pd.to_numeric(df["fear_greed"])

        # Compute features
        df["sentiment_rolling_3d"] = df["sentiment_score"].rolling(3).mean()
        df["sentiment_momentum"] = df["sentiment_score"] - df["sentiment_rolling_3d"]
        df["fear_greed_norm"] = df["fear_greed"] / 100.0

        # Drop NaNs (first 2 rows will have NaN for rolling 3d)
        df_valid = df.dropna(subset=["sentiment_rolling_3d", "sentiment_momentum", "fear_greed_norm"])

        if df_valid.empty:
            print(f"Computed sentiment features for {symbol}: 0 valid rows")
            continue

        records: List[Dict[str, Any]] = []
        for _, row in df_valid.iterrows():
            records.append({
                "asset_id": asset_id,
                "timestamp": row["timestamp"].isoformat(),
                "sentiment_rolling_3d": row["sentiment_rolling_3d"],
                "sentiment_momentum": row["sentiment_momentum"],
                "fear_greed_norm": row["fear_greed_norm"]
            })

        # Batch upsert
        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            try:
                supabase.table("sentiment").upsert(batch, on_conflict="asset_id,timestamp").execute()
            except Exception as e:
                print(f"Error upserting sentiment features for {symbol}: {e}")

        print(f"Computed sentiment features for {symbol}")

    print("✅ Sentiment features complete")

if __name__ == "__main__":
    main()
