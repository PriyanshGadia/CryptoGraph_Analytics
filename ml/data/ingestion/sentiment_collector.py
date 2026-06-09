import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
COINGECKO_BASE_URL: str = os.environ.get("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")

COIN_IDS: Dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "LINK": "chainlink",
    "DOT": "polkadot", "MATIC": "matic-network", "UNI": "uniswap",
    "ATOM": "cosmos", "LTC": "litecoin", "BCH": "bitcoin-cash",
    "XLM": "stellar", "ALGO": "algorand", "AAVE": "aave",
    "MKR": "maker", "COMP": "compound-governance-token",
    "CRV": "curve-dao-token", "NEAR": "near", "SAND": "the-sandbox",
    "MANA": "decentraland", "AXS": "axie-infinity", "SUSHI": "sushi",
    "BAL": "balancer", "SNX": "havven", "YFI": "yearn-finance",
    "ZRX": "0x", "VET": "vechain", "FIL": "filecoin", "TRX": "tron",
    "THETA": "theta-token", "XMR": "monero", "EOS": "eos",
    "LRC": "loopring", "BAT": "basic-attention-token", "ZEC": "zcash",
    "DASH": "dash", "ICX": "icon", "QTUM": "qtum", "ONT": "ontology",
    "ZIL": "zilliqa", "IOTA": "iota", "WAVES": "waves",
    "DGB": "digibyte", "1INCH": "1inch", "FTM": "fantom",
    "REN": "republic-protocol"
}

def get_asset_id(symbol: str) -> Optional[str]:
    """Retrieve the UUID of an asset from the database by its symbol."""
    try:
        response = supabase.table("assets").select("id").eq("symbol", symbol).execute()
        if response.data:
            return response.data[0]["id"]
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Database error querying asset {symbol}: {e}")
    return None

def fetch_coin_sentiment(coin_id: str) -> Optional[Dict[str, Any]]:
    """Fetch community and sentiment data from CoinGecko, handling rate limits."""
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "false",
        "community_data": "true",
        "developer_data": "false"
    }
    
    while True:
        try:
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 429:
                print("Rate limit reached (429). Sleeping 60s...")
                time.sleep(60)
                continue
                
            resp.raise_for_status()
            return resp.json()
            
        except requests.RequestException as e:
            sentry_sdk.capture_exception(e)
            print(f"Error fetching data for {coin_id}: {e}")
            return None

def main() -> None:
    now = datetime.now(timezone.utc)
    # Using start of the day UTC for consistency
    today_ts = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat()
    
    assets_collected = 0

    for symbol, coin_id in COIN_IDS.items():
        data = fetch_coin_sentiment(coin_id)
        if not data:
            print(f"Skipping {symbol} due to missing data.")
            time.sleep(1.5)
            continue
            
        # Extract response
        sentiment_up_pct = data.get("sentiment_votes_up_percentage")
        community_data = data.get("community_data", {})
        
        community_score = community_data.get("community_score")
        public_interest = community_data.get("public_interest_score")
        
        if sentiment_up_pct is not None:
            sentiment_score = (sentiment_up_pct / 100.0) * 2.0 - 1.0
        else:
            sentiment_score = None

        asset_id = get_asset_id(symbol)
        if not asset_id:
            print(f"Asset {symbol} not found in database, skipping.")
            time.sleep(1.5)
            continue

        # Upsert record
        record = {
            "asset_id": asset_id,
            "timestamp": today_ts,
            "sentiment_score": sentiment_score,
            "community_score": community_score,
            "public_interest": public_interest,
            "news_volume": 0  # not available in free tier
        }
        
        try:
            supabase.table("sentiment").upsert(
                record, 
                on_conflict="asset_id,timestamp"
            ).execute()
            assets_collected += 1
            print(f"Collected sentiment for {symbol}")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Error upserting sentiment for {symbol}: {e}")
        
        # Respect rate limit
        time.sleep(1.5)
        
    print(f"✅ Sentiment collection complete for {assets_collected} assets")

if __name__ == "__main__":
    main()
