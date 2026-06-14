import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Wilder's Smoothing Method (WSMA) used by TradingView
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd = fast_ema - slow_ema
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd, macd_signal

def main():
    conn = sqlite3.connect(DB_PATH)
    
    # Ensure table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS technical_features (
            asset_id TEXT,
            timestamp TEXT,
            rsi_14 REAL,
            macd REAL,
            macd_signal REAL,
            atr_14 REAL,
            bb_width REAL,
            returns_1d REAL,
            returns_7d REAL,
            volatility_7d REAL,
            PRIMARY KEY (asset_id, timestamp)
        )
    """)
    
    # Get all assets
    assets = conn.execute("SELECT id, symbol FROM assets").fetchall()
    
    for asset_id, symbol in assets:
        df = pd.read_sql_query(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE asset_id = ? ORDER BY timestamp",
            conn, params=(asset_id,)
        )
        if df.empty:
            continue
            
        # Calculate Technicals
        df['returns_1d'] = df['close'].pct_change().fillna(0)
        df['returns_7d'] = df['close'].pct_change(7).fillna(0)
        df['volatility_7d'] = df['returns_1d'].rolling(7).std().fillna(0)
        
        df['rsi_14'] = calculate_rsi(df['close'], 14).fillna(50)
        df['macd'], df['macd_signal'] = calculate_macd(df['close'])
        
        # ATR and BB skipped for brevity, set to 0
        df['atr_14'] = 0.0
        df['bb_width'] = 0.0
        
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        records = []
        for _, row in df.iterrows():
            records.append((
                asset_id, row['timestamp'], row['rsi_14'], row['macd'], row['macd_signal'],
                row['atr_14'], row['bb_width'], row['returns_1d'], row['returns_7d'], row['volatility_7d']
            ))
            
        conn.executemany("""
            INSERT INTO technical_features 
            (asset_id, timestamp, rsi_14, macd, macd_signal, atr_14, bb_width, returns_1d, returns_7d, volatility_7d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, timestamp) DO UPDATE SET
                rsi_14=excluded.rsi_14,
                macd=excluded.macd,
                macd_signal=excluded.macd_signal,
                returns_1d=excluded.returns_1d,
                returns_7d=excluded.returns_7d,
                volatility_7d=excluded.volatility_7d
        """, records)
        conn.commit()
        print(f"Computed technicals for {symbol} ({len(records)} rows)")
        
    conn.close()

if __name__ == "__main__":
    main()
