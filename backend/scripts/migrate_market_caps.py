import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cryptograph.db"))
print(f"Connecting to database at {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

FALLBACK_CIRCULATING_SUPPLIES = {
    "SUI": 2600000000.0,
    "APT": 490000000.0,
    "ARB": 2900000000.0,
    "JUP": 1350000000.0,
    "POL": 8000000000.0,
    "TON": 2500000000.0,
    "UNI": 600000000.0,
    "MATIC": 9900000000.0,
    "GRT": 9540000000.0,
    "MKR": 930000.0,
    "OCEAN": 568000000.0,
    "STX": 1460000000.0,
    "TAO": 7000000.0,
    "CORE": 400000.0,
    "EOS": 1120000000.0,
}

for symbol, supply in FALLBACK_CIRCULATING_SUPPLIES.items():
    cursor.execute("SELECT id FROM assets WHERE symbol = ?", (symbol,))
    res = cursor.fetchone()
    if not res:
        print(f"Asset {symbol} not found in database.")
        continue
    asset_id = res[0]
    cursor.execute("SELECT close FROM ohlcv WHERE asset_id = ? ORDER BY timestamp DESC LIMIT 1", (asset_id,))
    price_res = cursor.fetchone()
    if not price_res:
        print(f"No price found for {symbol} in ohlcv.")
        continue
    price = price_res[0]
    mcap = supply * price
    cursor.execute("UPDATE assets SET market_cap_usd = ? WHERE id = ?", (mcap, asset_id))
    print(f"Updated {symbol}: close={price:.6f}, supply={supply:,.0f}, mcap=${mcap:,.2f}")

conn.commit()
conn.close()
print("Market cap migration completed successfully!")
