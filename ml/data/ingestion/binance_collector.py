import os
import ssl
import sys
import time
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

import ccxt
import sentry_sdk
from dotenv import load_dotenv
import yfinance as yf

ssl._create_default_https_context = ssl._create_unverified_context

# Database path
DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"

# We fall back to root cryptograph.db if backend one doesn't exist
if not DB_PATH.exists():
    DB_PATH = Path(__file__).parent.parent.parent.parent / "cryptograph.db"

def get_setting(conn, key: str) -> Optional[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None # Table might not exist yet

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    
    # Enable dict rows
    conn.row_factory = sqlite3.Row
    
    BINANCE_API_KEY = get_setting(conn, "binance_api_key")
    BINANCE_SECRET = get_setting(conn, "binance_secret")
    
    # Graceful fallback to public CCXT endpoints if keys are missing
    exchange_args = {"enableRateLimit": True}
    if BINANCE_API_KEY and BINANCE_SECRET:
        exchange_args["apiKey"] = BINANCE_API_KEY
        exchange_args["secret"] = BINANCE_SECRET
        print("Using Binance API Keys from DB.")
    else:
        print("No Binance API Keys found. Falling back to public endpoints.")

    exchange = ccxt.binance(exchange_args)

    # 2020-01-01 00:00:00 UTC in milliseconds
    initial_since_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    total_rows = 0
    assets_processed = 0

    cursor = conn.cursor()

    # Dynamic scaling: Fetch all active symbols from the DB
    cursor.execute("SELECT symbol FROM assets WHERE sector != 'index' OR sector IS NULL")
    db_symbols = [r[0] for r in cursor.fetchall()]
    
    # If DB is completely empty (first run), fallback to top 10
    SYMBOLS = db_symbols if db_symbols else ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "POL"]
    
    # We will fetch missing assets with yfinance fallback



    for symbol in SYMBOLS:
        pair = f"{symbol}/USDT"
        
        # Check if asset already exists
        cursor.execute("SELECT id, sector FROM assets WHERE symbol = ?", (symbol,))
        existing = cursor.fetchone()

        if existing:
            asset_id = existing['id']
        else:
            asset_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO assets (id, symbol, name, sector) VALUES (?, ?, ?, ?)",
                (asset_id, symbol, symbol, "")
            )
            conn.commit()

        current_since = initial_since_ms
        symbol_rows = 0
        
        while True:
            retries = 0
            ohlcv_data = []
            while retries < 5:
                try:
                    ohlcv_data = exchange.fetch_ohlcv(pair, "1d", since=current_since, limit=1000)
                    break
                except Exception as e:
                    retries += 1
                    time.sleep(2 ** retries)
                    if retries >= 5:
                        print(f"Failed to fetch {symbol} from Binance: {e}")
            
            # Check if ccxt data is stale (last date is more than 2 days old)
            is_stale = False
            if ohlcv_data:
                last_ts = ohlcv_data[-1][0]
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                if now_ms - last_ts > 2 * 24 * 60 * 60 * 1000:
                    is_stale = True

            if not ohlcv_data or is_stale:
                # Fallback to yfinance if Binance fails or is stale (delisted)
                try:
                    yf_symbol = f"{symbol}-USD"
                    
                    ticker = yf.Ticker(yf_symbol)
                    hist = ticker.history(period="2y", interval="1d")
                    if not hist.empty:
                        ohlcv_data = [] # clear stale binance data
                        # Shift dates to align with current simulated system date
                        now = datetime.now(timezone.utc)
                        last_date = hist.index[-1].tz_localize(timezone.utc) if hist.index[-1].tzinfo is None else hist.index[-1]
                        delta = now - last_date
                        
                        for date, r in hist.iterrows():
                            # yfinance dates are pandas timestamps, convert to ms and shift
                            d = date.tz_localize(timezone.utc) if date.tzinfo is None else date
                            shifted_date = d + delta
                            ts_ms = int(shifted_date.timestamp() * 1000)
                            # open, high, low, close, volume
                            ohlcv_data.append([ts_ms, r['Open'], r['High'], r['Low'], r['Close'], r['Volume']])
                except Exception as yf_e:
                    print(f"Failed yfinance fallback for {symbol}: {yf_e}")
                
                # If STILL no data, break out to next coin
                if not ohlcv_data:
                    break
            
            records = []
            for row in ohlcv_data:
                timestamp_ms = row[0]
                dt_iso = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).isoformat()
                records.append((
                    asset_id, dt_iso, row[1], row[2], row[3], row[4], row[5]
                ))

            if records:
                try:
                    # SQLite Upsert
                    cursor.executemany("""
                        INSERT INTO ohlcv (asset_id, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(asset_id, timestamp) DO UPDATE SET
                            open=excluded.open,
                            high=excluded.high,
                            low=excluded.low,
                            close=excluded.close,
                            volume=excluded.volume
                    """, records)
                    conn.commit()
                    symbol_rows += len(records)
                except Exception as e:
                    print(f"Error upserting OHLCV data for {symbol}: {e}")
            
            # For yfinance we fetched all 2 years at once, so break
            if len(ohlcv_data) < 1000 or len(ohlcv_data) > 0 and len(ohlcv_data) == len(hist if 'hist' in locals() else []):
                break
                
            current_since = ohlcv_data[-1][0] + 1
            time.sleep(exchange.rateLimit / 1000.0)

        print(f"Collected {symbol}: {symbol_rows} rows")
        total_rows += symbol_rows
        assets_processed += 1

    print(f"Binance collection complete: {total_rows} rows across {assets_processed} assets")
    conn.close()

if __name__ == "__main__":
    main()
