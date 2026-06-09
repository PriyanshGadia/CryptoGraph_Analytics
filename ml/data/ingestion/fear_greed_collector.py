import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import sentry_sdk
from dotenv import load_dotenv
from supabase import Client, create_client

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SENTRY_DSN: Optional[str] = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)

SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE keys must be set in ml/.env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
FEAR_GREED_URL: str = "https://api.alternative.me/fng/?limit=1000"

def get_all_assets() -> List[str]:
    """Retrieve all asset UUIDs from the assets table."""
    try:
        response = supabase.table("assets").select("id").execute()
        return [row["id"] for row in response.data]
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Error fetching assets from database: {e}")
        return []

def main() -> None:
    try:
        resp = requests.get(FEAR_GREED_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        sentry_sdk.capture_exception(e)
        print(f"Error fetching Fear & Greed data: {e}")
        sys.exit(1)

    fng_data: List[Dict[str, Any]] = data.get("data", [])
    if not fng_data:
        print("No Fear & Greed data returned.")
        return

    asset_ids = get_all_assets()
    if not asset_ids:
        print("No assets found in database. Skipping sentiment updates.")
        return

    records: List[Dict[str, Any]] = []
    
    for entry in fng_data:
        timestamp_unix = int(entry["timestamp"])
        dt = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
        ts_iso = dt.isoformat()
        fear_greed_val = int(entry["value"])

        # Upsert one row per asset
        for asset_id in asset_ids:
            records.append({
                "asset_id": asset_id,
                "timestamp": ts_iso,
                "fear_greed": fear_greed_val
            })

    # Batch upsert into sentiment table
    # on_conflict limits the update to fear_greed
    batch_size = 500
    total_upserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            supabase.table("sentiment").upsert(
                batch, 
                on_conflict="asset_id,timestamp"
            ).execute()
            total_upserted += len(batch)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Error upserting Fear & Greed batch: {e}")

    print(f"Collected {len(fng_data)} fear & greed data points across {len(asset_ids)} assets")

if __name__ == "__main__":
    main()
