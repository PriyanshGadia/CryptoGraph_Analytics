import sqlite3
import os
import ccxt
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import sys
import os

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, base_dir)
db_path = os.path.join(base_dir, "cryptograph.db")

def main():
    if not os.path.exists(db_path):
        print("Database not found. Initializing...")
    else:
        # Check if empty
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT COUNT(*) FROM assets")
            count = c.fetchone()[0]
            if count > 0:
                print("Database is already populated.")
                return
        except Exception:
            pass # Tables might not exist
        conn.close()

    print("Database is empty! Running rapid seed for Termux...")
    
    # Ensure tables exist
    from app.db.database import engine, Base
    import app.db.models_sqla as models
    Base.metadata.create_all(bind=engine)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    exchange = ccxt.binance({"enableRateLimit": True})
    symbols = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
        "MATIC", "UNI", "BCH", "LTC", "NEAR", "APT", "ICP", "STX", "FIL", "ATOM",
        "XMR", "AR", "HBAR", "VET", "MKR", "INJ", "GRT", "OP", "THETA", "LDO",
        "FET", "FTM", "TAO", "TIA", "SEI", "SUI", "PYTH", "JUP", "GALA", "AAVE",
        "ALGO", "SAND", "EGLD", "QNT", "SNX", "AXS", "CHZ", "MANA", "MINA", "DYDX"
    ]
    
    since = int((datetime.now(timezone.utc) - timedelta(days=65)).timestamp() * 1000)

    for sym in symbols:
        asset_id = str(uuid.uuid4())
        c.execute("INSERT INTO assets (id, symbol, name, sector) VALUES (?, ?, ?, ?)", (asset_id, sym, sym, "Layer 1"))
        print(f"Fetching 65 days of OHLCV for {sym}...")
        try:
            ohlcv = exchange.fetch_ohlcv(f"{sym}/USDT", "1d", since=since, limit=100)
            
            # Insert OHLCV
            for row in ohlcv:
                ts = datetime.fromtimestamp(row[0]/1000, tz=timezone.utc).isoformat()
                c.execute("INSERT INTO ohlcv (asset_id, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (asset_id, ts, row[1], row[2], row[3], row[4], row[5]))
                
            # Insert fake technical features with variance to prevent NaN correlation tensors
            # Using actual returns from OHLCV
            prev_close = None
            for row in ohlcv:
                ts = datetime.fromtimestamp(row[0]/1000, tz=timezone.utc).isoformat()
                close = row[4]
                returns_1d = (close - prev_close) / prev_close if prev_close else 0.0
                prev_close = close
                c.execute("""INSERT INTO technical_features 
                          (asset_id, timestamp, rsi_14, returns_1d, returns_7d, volatility_7d, macd, macd_signal, atr_14, bb_width) 
                          VALUES (?, ?, 50.0, ?, 0.0, 0.05, 0.0, 0.0, 10.0, 0.1)""",
                          (asset_id, ts, returns_1d))
                          
            # Insert fake prediction
            c.execute("INSERT INTO predictions (asset_id, timestamp, predicted_at, direction, confidence, volatility_regime) VALUES (?, ?, ?, ?, ?, ?)",
                      (asset_id, ts, datetime.now(timezone.utc).isoformat(), "strong_up", 85.5, "medium"))

        except Exception as e:
            print(f"Failed to fetch {sym}: {e}")

    conn.commit()
    conn.close()
    print("Rapid seed complete. Frontend will now have data!")

if __name__ == "__main__":
    main()
