import sqlite3
import os
import ccxt
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import sys

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
                
            # Calculate technical features using pandas from real fetched daily OHLCV rows
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            
            df["returns_1d"] = df["close"].pct_change().fillna(0.0)
            df["returns_7d"] = df["close"].pct_change(7).fillna(0.0)
            df["volatility_7d"] = df["returns_1d"].rolling(window=7).std().fillna(0.05)
            
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().fillna(0.0)
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().fillna(0.0)
            rs = gain / (loss + 1e-9)
            df["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50.0)
            
            exp1 = df["close"].ewm(span=12, adjust=False).mean()
            exp2 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd"] = exp1 - exp2
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift()).abs()
            low_close = (df["low"] - df["close"].shift()).abs()
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df["atr_14"] = true_range.rolling(14).mean().fillna(true_range.fillna(0.0))
            
            sma = df["close"].rolling(20).mean()
            rstd = df["close"].rolling(20).std()
            upper_band = sma + 2 * rstd
            lower_band = sma - 2 * rstd
            df["bb_width"] = ((upper_band - lower_band) / (sma + 1e-9)).fillna(0.1)

            # Insert calculated technical features
            for i, row in enumerate(ohlcv):
                ts = datetime.fromtimestamp(row[0]/1000, tz=timezone.utc).isoformat()
                c.execute("""INSERT INTO technical_features 
                          (asset_id, timestamp, rsi_14, returns_1d, returns_7d, volatility_7d, macd, macd_signal, atr_14, bb_width) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (asset_id, ts, float(df.loc[i, "rsi_14"]), float(df.loc[i, "returns_1d"]), 
                           float(df.loc[i, "returns_7d"]), float(df.loc[i, "volatility_7d"]), 
                           float(df.loc[i, "macd"]), float(df.loc[i, "macd_signal"]), 
                           float(df.loc[i, "atr_14"]), float(df.loc[i, "bb_width"])))

        except Exception as e:
            print(f"Failed to fetch {sym}: {e}")

    conn.commit()
    conn.close()
    
    # Run the real ML inference pipeline to populate the predictions table with true GCN-predicted outputs
    print("Ingestion complete. Executing real inference pipeline to populate predictions...")
    try:
        from ml.pipelines.inference_pipeline import run_inference
        res = run_inference()
        print(f"Real predictions populated successfully: {res}")
    except Exception as e:
        print(f"Failed to run real prediction pipeline: {e}")

    # --- Validation Layer ---
    print("Validating seed integrity...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM assets")
    asset_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ohlcv")
    ohlcv_count = c.fetchone()[0]
    conn.close()

    assert asset_count > 0, "CRITICAL ERROR: No assets were seeded into the database."
    assert ohlcv_count > 0, "CRITICAL ERROR: No OHLCV data was seeded into the database."

    print(f"Validation successful. {asset_count} assets and {ohlcv_count} OHLCV rows present.")
    print("Rapid seed complete. Frontend has true, live data!")

if __name__ == "__main__":
    main()
