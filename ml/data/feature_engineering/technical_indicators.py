import os
import sys
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

def compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=length - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=length - 1, adjust=False).mean()

    rsi = pd.Series(index=close.index, dtype=float)
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    loss_zero = (avg_loss == 0) & (avg_gain > 0)
    normal = ~both_zero & ~loss_zero

    rsi[both_zero] = 50.0   # truly no movement at all — genuinely neutral
    rsi[loss_zero] = 100.0  # all gains, zero losses — maximally overbought, not neutral
    rs = avg_gain[normal] / avg_loss[normal]
    rsi[normal] = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)  # only reachable during the initial warm-up window

def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd, macd_signal

def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/length, adjust=False).mean()
    return atr

def compute_bb_width(close: pd.Series, length: int = 20, std: float = 2.0) -> pd.Series:
    bbm = close.rolling(window=length).mean()
    bbs = close.rolling(window=length).std()
    bbu = bbm + std * bbs
    bbl = bbm - std * bbs
    return (bbu - bbl) / bbm.replace(0, np.nan)

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
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
        df = df.sort_values("timestamp")
        
        # Ensure numerical types
        cols_to_numeric = ["open", "high", "low", "close", "volume"]
        df[cols_to_numeric] = df[cols_to_numeric].apply(pd.to_numeric)

        # Compute indicators using custom pure-python logic
        df["rsi_14"] = compute_rsi(df["close"], length=14)
        
        macd_val, macd_sig_val = compute_macd(df["close"], fast=12, slow=26, signal=9)
        df["macd"] = macd_val
        df["macd_signal"] = macd_sig_val
            
        df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], length=14)
        df["bb_width"] = compute_bb_width(df["close"], length=20, std=2.0)

        # Compute manual indicators
        df["returns_1d"] = np.log(df["close"] / df["close"].shift(1))
        df["returns_7d"] = np.log(df["close"] / df["close"].shift(7))
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
