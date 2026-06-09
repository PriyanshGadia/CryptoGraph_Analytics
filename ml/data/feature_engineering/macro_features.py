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

def main() -> None:
    # Query all macro_indicators rows ordered by timestamp ASC
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        res = (
            supabase.table("macro_indicators")
            .select("*")
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
        print("No macro indicators found.")
        return

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    cols = ["fed_rate", "cpi", "inflation", "vix"]
    for c in cols:
        df[c] = pd.to_numeric(df[c])

    # Forward-fill any remaining gaps up to 7 days
    df[cols] = df[cols].ffill(limit=7)

    # Compute rolling 252-day z-score
    for col in cols:
        rolling_mean = df[col].rolling(252, min_periods=30).mean()
        rolling_std = df[col].rolling(252, min_periods=30).std()
        
        # Avoid division by zero
        rolling_std = rolling_std.replace(0, pd.NA).ffill()
        
        z_col = f"{col}_z"
        df[z_col] = (df[col] - rolling_mean) / rolling_std

    # Drop NaNs created by rolling min_periods=30
    df_valid = df.dropna(subset=[f"{c}_z" for c in cols])

    records: List[Dict[str, Any]] = []
    for _, row in df_valid.iterrows():
        records.append({
            "timestamp": row["timestamp"].isoformat(),
            "fed_rate_z": row["fed_rate_z"],
            "cpi_z": row["cpi_z"],
            "inflation_z": row["inflation_z"],
            "vix_z": row["vix_z"]
        })

    # Upsert all rows back into macro_indicators
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            supabase.table("macro_indicators").upsert(batch, on_conflict="timestamp").execute()
        except Exception as e:
            print(f"Error upserting macro features: {e}")

    print(f"✅ Macro normalization complete: {len(records)} rows")

if __name__ == "__main__":
    main()
