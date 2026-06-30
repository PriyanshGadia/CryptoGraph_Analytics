import os
import ssl
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import yfinance as yf
from fredapi import Fred
# Database path
DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"
if not DB_PATH.exists():
    DB_PATH = Path(__file__).parent.parent.parent.parent / "cryptograph.db"

def get_setting(conn, key: str) -> Optional[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None

SERIES_MAP: Dict[str, str] = {
    "DFF": "fed_rate",
    "CPIAUCSL": "cpi",
    "T10YIE": "inflation",
    "VIXCLS": "vix"
}

def create_macro_table_if_not_exists(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL UNIQUE,
            fed_rate REAL,
            cpi REAL,
            inflation REAL,
            vix REAL,
            fed_rate_z REAL,
            cpi_z REAL,
            inflation_z REAL,
            vix_z REAL
        )
    """)
    conn.commit()

def fetch_yfinance_fallback() -> pd.DataFrame:
    """Fetch surrogate data via yfinance for missing FRED API."""
    print("FRED API key missing. Falling back to yfinance (^TNX, ^VIX).")
    tickers = ["^TNX", "^VIX"]
    data = yf.download(tickers, start="2020-01-01")
    
    df = pd.DataFrame()
    # Map ^TNX (10Y Yield) -> fed_rate proxy
    # Map ^VIX -> vix
    df['fed_rate'] = data['Close']['^TNX']
    df['vix'] = data['Close']['^VIX']
    df['cpi'] = None  # No easy daily proxy for CPI via yfinance
    df['inflation'] = None
    
    return df

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    create_macro_table_if_not_exists(conn)
    
    FRED_API_KEY = get_setting(conn, "fred_api_key")
    all_data = pd.DataFrame()

    if FRED_API_KEY:
        fred = Fred(api_key=FRED_API_KEY)
        for series_id, column_name in SERIES_MAP.items():
            try:
                data = fred.get_series(series_id, observation_start="2020-01-01")
                df = data.to_frame(name=column_name)
                
                if all_data.empty:
                    all_data = df
                else:
                    all_data = all_data.join(df, how="outer")
                print(f"Fetched FRED series: {series_id} ({len(data)} observations)")
            except Exception as e:
                print(f"Error fetching {series_id}: {e}")
    else:
        all_data = fetch_yfinance_fallback()

    if all_data.empty:
        print("No macro data collected.")
        return

    all_data = all_data.resample("D").last()
    all_data = all_data.ffill()
    all_data = all_data.dropna(how="all")

    records = []
    for timestamp, row in all_data.iterrows():
        records.append((
            timestamp.isoformat() + "Z",
            row.get("fed_rate") if pd.notna(row.get("fed_rate")) else None,
            row.get("cpi") if pd.notna(row.get("cpi")) else None,
            row.get("inflation") if pd.notna(row.get("inflation")) else None,
            row.get("vix") if pd.notna(row.get("vix")) else None
        ))

    cursor = conn.cursor()
    total_rows = 0
    for i in range(0, len(records), 500):
        batch = records[i:i+500]
        try:
            cursor.executemany("""
                INSERT INTO macro_indicators (timestamp, fed_rate, cpi, inflation, vix)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(timestamp) DO UPDATE SET
                    fed_rate=excluded.fed_rate,
                    cpi=excluded.cpi,
                    inflation=excluded.inflation,
                    vix=excluded.vix
            """, batch)
            conn.commit()
            total_rows += len(batch)
        except Exception as e:
            print(f"Error upserting macro batch: {e}")

    print(f"Macro collection complete: {total_rows} daily rows")
    conn.close()

if __name__ == "__main__":
    main()
