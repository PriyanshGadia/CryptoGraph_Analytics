import os
import ssl
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import sentry_sdk
from dotenv import load_dotenv
from fredapi import Fred
from supabase import Client, create_client

ssl._create_default_https_context = ssl._create_unverified_context


# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SENTRY_DSN: Optional[str] = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)

SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
FRED_API_KEY: Optional[str] = os.environ.get("FRED_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not FRED_API_KEY:
    print("Error: SUPABASE and FRED keys must be set in ml/.env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
fred = Fred(api_key=FRED_API_KEY)

SERIES_MAP: Dict[str, str] = {
    "DFF": "fed_rate",
    "CPIAUCSL": "cpi",
    "T10YIE": "inflation",
    "VIXCLS": "vix"
}

def main() -> None:
    all_data = pd.DataFrame()

    for series_id, column_name in SERIES_MAP.items():
        try:
            # Fetch series
            data = fred.get_series(series_id, observation_start="2020-01-01")
            df = data.to_frame(name=column_name)
            
            # Combine into one DataFrame on the date index
            if all_data.empty:
                all_data = df
            else:
                all_data = all_data.join(df, how="outer")
                
            print(f"Fetched FRED series: {series_id} ({len(data)} observations)")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Error fetching {series_id}: {e}")

    if all_data.empty:
        print("No FRED data collected.")
        return

    # Resample to daily frequency using .resample("D").last()
    # Note: 'D' resamples to calendar day frequency
    all_data = all_data.resample("D").last()
    
    # Forward-fill missing values (weekends/holidays)
    all_data = all_data.ffill()
    
    # Drop rows where ALL four columns are NaN
    all_data = all_data.dropna(how="all")

    # Upsert into macro_indicators table
    # Supabase upsert has a limit, typically 1000 or so, we will do batches
    records = []
    for timestamp, row in all_data.iterrows():
        # Pandas timestamp has an isoformat method
        records.append({
            "timestamp": timestamp.isoformat() + "Z",
            "fed_rate": row["fed_rate"] if pd.notna(row["fed_rate"]) else None,
            "cpi": row["cpi"] if pd.notna(row["cpi"]) else None,
            "inflation": row["inflation"] if pd.notna(row["inflation"]) else None,
            "vix": row["vix"] if pd.notna(row["vix"]) else None
        })

    total_rows = 0
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            supabase.table("macro_indicators").upsert(batch, on_conflict="timestamp").execute()
            total_rows += len(batch)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Error upserting macro batch: {e}")

    print(f"✅ FRED collection complete: {total_rows} daily rows")

if __name__ == "__main__":
    main()
