import os
import sys
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pandas_ta as ta  # noqa: F401

DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"

def get_assets(conn) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol FROM assets")
    return cursor.fetchall()

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    assets = get_assets(conn)
    if not assets:
        print("No assets found in database.")
        conn.close()
        return

    cursor = conn.cursor()

    for asset in assets:
        asset_id = asset["id"]
        symbol = asset["symbol"]

        cursor.execute(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE asset_id = ? ORDER BY timestamp ASC",
            (asset_id,)
        )
        all_rows = cursor.fetchall()

        if not all_rows:
            continue

        df = pd.DataFrame([dict(r) for r in all_rows])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        
        # Ensure numerical types
        cols_to_numeric = ["open", "high", "low", "close", "volume"]
        df[cols_to_numeric] = df[cols_to_numeric].apply(pd.to_numeric)

        # Compute pandas-ta indicators
        df["rsi_14"] = df.ta.rsi(length=14)
        
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df["macd"] = macd["MACD_12_26_9"]
            df["macd_signal"] = macd["MACDs_12_26_9"]
        else:
            df["macd"] = np.nan
            df["macd_signal"] = np.nan
            
        df["atr_14"] = df.ta.atr(length=14)
        
        bb = df.ta.bbands(length=20, std=2)
        if bb is not None and not bb.empty:
            bbu = bb["BBU_20_2.0_2.0"]
            bbl = bb["BBL_20_2.0_2.0"]
            bbm = bb["BBM_20_2.0_2.0"]
            df["bb_width"] = (bbu - bbl) / bbm
        else:
            df["bb_width"] = np.nan

        # Compute manual indicators
        df["returns_1d"] = np.log(df["close"] / df["close"].shift(1))
        df["returns_7d"] = (df["close"] - df["close"].shift(7)) / df["close"].shift(7)
        df["volatility_7d"] = df["returns_1d"].rolling(7).std()

        # Drop rows where any column is NaN (indicator warm-up)
        df = df.dropna()

        if df.empty:
            print(f"Computed features for {symbol}: 0 rows (after dropping NaNs)")
            continue

        # Prepare records for upsert
        records = []
        for _, row in df.iterrows():
            records.append((
                asset_id,
                row["timestamp"].isoformat(),
                row["rsi_14"],
                row["macd"],
                row["macd_signal"],
                row["atr_14"],
                row["bb_width"],
                row["returns_1d"],
                row["returns_7d"],
                row["volatility_7d"]
            ))

        # Batch upsert to SQLite
        try:
            cursor.executemany("""
                INSERT INTO technical_features 
                (asset_id, timestamp, rsi_14, macd, macd_signal, atr_14, bb_width, returns_1d, returns_7d, volatility_7d)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, timestamp) DO UPDATE SET
                    rsi_14=excluded.rsi_14,
                    macd=excluded.macd,
                    macd_signal=excluded.macd_signal,
                    atr_14=excluded.atr_14,
                    bb_width=excluded.bb_width,
                    returns_1d=excluded.returns_1d,
                    returns_7d=excluded.returns_7d,
                    volatility_7d=excluded.volatility_7d
            """, records)
            conn.commit()
            print(f"Computed features for {symbol}: {len(records)} rows")
        except Exception as e:
            print(f"Error upserting technical features for {symbol}: {e}")

    print("Technical indicators complete")
    conn.close()

if __name__ == "__main__":
    main()
