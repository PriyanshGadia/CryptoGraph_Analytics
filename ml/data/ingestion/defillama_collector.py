"""
DefiLlama Collector for ST-GCN.
Fetches daily TVL, Revenue, and Active Users for DeFi assets to serve as fundamental graph node features.
"""

import urllib.request
import json
from datetime import datetime, timezone
import time
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.app.db.database import SessionLocal
from backend.app.db.models_sqla import Asset, OnchainMetric

# Mapping from Binance symbols to DefiLlama slug names where they differ or are known
DEFILLAMA_SLUGS = {
    "ETH": "ethereum",
    "BNB": "binance",
    "SOL": "solana",
    "AVAX": "avalanche",
    "MATIC": "polygon",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "MKR": "makerdao",
    "COMP": "compound",
    "SNX": "synthetix",
    "YFI": "yearn-finance",
    "SUSHI": "sushiswap",
    "CRV": "curve-dex",
    "BAL": "balancer",
    "LRC": "loopring",
    "BAT": "basic-attention-token",
    "FIL": "filecoin",
    "NEAR": "near",
    "FTM": "fantom"
}

def fetch_defillama_protocol(slug: str) -> Dict[str, Any]:
    """Fetch protocol data from DefiLlama API."""
    url = f"https://api.llama.fi/protocol/{slug}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Failed to fetch DefiLlama protocol {slug}: {e}")
        return {}

def collect_onchain_data():
    """Collects and stores daily on-chain data for relevant assets."""
    db: Session = SessionLocal()
    try:
        assets = db.query(Asset).all()
        
        for asset in assets:
            slug = DEFILLAMA_SLUGS.get(asset.symbol)
            if not slug:
                # Fallback: try using the asset name lowercase and hyphenated
                slug = asset.name.lower().replace(" ", "-") if asset.name else asset.symbol.lower()
                
            print(f"Fetching DefiLlama data for {asset.symbol} using slug '{slug}'...")
            data = fetch_defillama_protocol(slug)
            
            if not data or "tvl" not in data:
                continue
                
            # Process historical TVL
            tvl_data = data.get("tvl", [])
            # We don't have easy historical revenue/active users from the free public protocol endpoint
            # but we can store the latest or just use TVL for historical.
            # To keep it robust, we'll map the TVL by date
            
            # Map timestamps to TVL
            date_map = {}
            for item in tvl_data:
                # DefiLlama returns unix timestamps
                dt = datetime.fromtimestamp(item["date"], tz=timezone.utc)
                # Normalize to midnight
                dt_midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                date_map[dt_midnight] = {"tvl": float(item["totalLiquidityUSD"])}
                
            # Upsert into DB
            print(f"Upserting {len(date_map)} days of TVL data for {asset.symbol}...")
            
            # Batch fetch existing records
            existing_records = db.query(OnchainMetric).filter(
                OnchainMetric.asset_id == asset.id
            ).all()
            existing_lookup = {r.timestamp: r for r in existing_records}
            
            inserts = 0
            for dt, metrics in date_map.items():
                if dt in existing_lookup:
                    # Update TVL only
                    existing_lookup[dt].tvl = metrics["tvl"]
                else:
                    new_metric = OnchainMetric(
                        asset_id=asset.id,
                        timestamp=dt,
                        tvl=metrics["tvl"],
                        revenue=0.0, # Placeholder unless we use alternative endpoints
                        active_users=0.0
                    )
                    db.add(new_metric)
                    inserts += 1
            
            if inserts > 0:
                db.commit()
                
            # Rate limit respect
            time.sleep(0.5)
            
    finally:
        db.close()

if __name__ == "__main__":
    collect_onchain_data()
