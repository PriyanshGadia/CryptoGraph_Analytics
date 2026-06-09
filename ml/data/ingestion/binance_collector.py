import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import ccxt
import sentry_sdk
from dotenv import load_dotenv
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
BINANCE_API_KEY: Optional[str] = os.environ.get("BINANCE_API_KEY")
BINANCE_SECRET: Optional[str] = os.environ.get("BINANCE_SECRET")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in ml/.env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SYMBOLS: List[str] = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
    "MATIC", "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "FIL", "TRX",
    "NEAR", "SAND", "MANA", "AXS", "THETA", "XMR", "EOS", "AAVE", "MKR", "COMP",
    "SNX", "YFI", "SUSHI", "CRV", "BAL", "ZRX", "REN", "LRC", "BAT", "ZEC",
    "DASH", "WAVES", "ICX", "QTUM", "ONT", "ZIL", "IOTA", "DGB", "1INCH", "FTM"
]

def fetch_ohlcv_with_backoff(
    exchange: ccxt.Exchange, 
    symbol: str, 
    timeframe: str, 
    since: int, 
    limit: int = 1000
) -> List[List[Any]]:
    """Fetch OHLCV data from CCXT with exponential backoff for network and rate limit errors."""
    retries = 0
    delay = 1
    max_retries = 5

    while retries < max_retries:
        try:
            return exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        except (ccxt.NetworkError, ccxt.RateLimitExceeded) as e:
            retries += 1
            if retries >= max_retries:
                sentry_sdk.capture_exception(e)
                print(f"Failed to fetch {symbol} after {max_retries} retries: {e}")
                return []
            time.sleep(delay)
            delay *= 2
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Unexpected error fetching {symbol}: {e}")
            return []
            
    return []

def main() -> None:
    exchange = ccxt.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET,
        "enableRateLimit": True,
    })

    # 2020-01-01 00:00:00 UTC in milliseconds
    initial_since_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    total_rows = 0
    assets_processed = 0

    # Known delisted or unavailable symbols on Binance
    SKIP_SYMBOLS = {"REN", "WAVES", "ONT", "IOTA", "DGB"}

    for symbol in SYMBOLS:
        if symbol in SKIP_SYMBOLS:
            print(f"Skipping {symbol} — not available on Binance")
            continue
        pair = f"{symbol}/USDT"
        
        # Check if asset already exists with sector data
        asset_id = None
        try:
            existing = (supabase.table("assets")
                .select("id, symbol, sector, market_cap_usd")
                .eq("symbol", symbol)
                .execute())

            if existing.data:
                # Asset exists — only update if sector is missing/empty
                asset_id = existing.data[0]["id"]
                existing_sector = existing.data[0].get("sector", "")
                if not existing_sector or existing_sector in ("", "EMPTY", None):
                    # Only update sector if it's currently blank
                    supabase.table("assets").update({
                        "name": symbol
                    }).eq("id", asset_id).execute()
            else:
                # Asset doesn't exist — insert it with empty sector
                # (enrich_assets.py will fill in sector and market_cap later)
                result = supabase.table("assets").insert({
                    "symbol": symbol,
                    "name": symbol,
                    "sector": "",
                    "market_cap_usd": None
                }).execute()
                asset_id = result.data[0]["id"] if result.data else None

            if not asset_id:
                # Fallback: just get the id
                res = supabase.table("assets").select("id").eq(
                    "symbol", symbol).execute()
                asset_id = res.data[0]["id"] if res.data else None

            if not asset_id:
                print(f"Warning: Could not fetch/create asset for {symbol}")
                continue
        except Exception as e:
            sentry_sdk.capture_exception(e)
            print(f"Database error while upserting asset {symbol}: {e}")
            continue

        current_since = initial_since_ms
        symbol_rows = 0
        
        while True:
            ohlcv_data = fetch_ohlcv_with_backoff(exchange, pair, "1d", current_since, limit=1000)
            if not ohlcv_data:
                break
            
            records: List[Dict[str, Any]] = []
            for row in ohlcv_data:
                timestamp_ms = row[0]
                records.append({
                    "asset_id": asset_id,
                    "timestamp": datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).isoformat(),
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5]
                })

            if records:
                try:
                    supabase.table("ohlcv").upsert(records, on_conflict="asset_id,timestamp").execute()
                    symbol_rows += len(records)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    print(f"Error upserting OHLCV data for {symbol}: {e}")
            
            # If we fetched fewer than limit, we reached the end
            if len(ohlcv_data) < 1000:
                break
                
            # Next iteration from the last timestamp + 1 ms to avoid duplication
            current_since = ohlcv_data[-1][0] + 1
            time.sleep(exchange.rateLimit / 1000.0)

        print(f"Collected {symbol}: {symbol_rows} rows")
        total_rows += symbol_rows
        assets_processed += 1

    print(f"✅ Binance collection complete: {total_rows} rows across {assets_processed} assets")

if __name__ == "__main__":
    main()
