import sqlite3
import yfinance as yf
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def fetch_asset_info(yf_symbol: str) -> dict:
    ticker = yf.Ticker(yf_symbol)
    return ticker.info

def enrich_assets():
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[2] / 'cryptograph.db'
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, symbol FROM assets")
    assets = cursor.fetchall()
    
    print(f"Found {len(assets)} assets. Fetching data from yfinance...")
    
    for asset_id, symbol in assets:
        yf_symbol = f"{symbol}-USD"
        print(f"Fetching {yf_symbol}...")
        try:
            info = {}
            try:
                info = fetch_asset_info(yf_symbol)
            except Exception as yf_err:
                print(f"  -> yfinance fetch failed for {symbol}: {yf_err}")
            
            symbol_upper = symbol.upper()
            if symbol_upper in FALLBACK_CIRCULATING_SUPPLIES:
                supply = FALLBACK_CIRCULATING_SUPPLIES[symbol_upper]
                price = 0.0
                try:
                    cursor.execute("SELECT close FROM ohlcv WHERE asset_id = ? ORDER BY timestamp DESC LIMIT 1", (asset_id,))
                    db_price_row = cursor.fetchone()
                    if db_price_row:
                        price = db_price_row[0]
                except Exception as db_err:
                    print(f"  -> Error fetching db price: {db_err}")
                if price > 0:
                    mcap = supply * price
            else:
                mcap = info.get("marketCap", 0.0) if info else 0.0
                if not mcap:
                    circ_supply = info.get("circulatingSupply", 0.0) if info else 0.0
                    price = info.get("previousClose", 0.0) if info else 0.0
                    mcap = circ_supply * price
                
            # Map sectors using our canonical SECTORS dictionary from edge_types.py
            sector = info.get("sector", None)
            if not sector or sector == 'Cryptocurrency':
                found_sector = None
                try:
                    import sys
                    from pathlib import Path
                    root_dir = str(Path(__file__).resolve().parents[3])
                    if root_dir not in sys.path:
                        sys.path.append(root_dir)
                    from ml.graph.edge_types import SECTORS
                    for sec, symbols_list in SECTORS.items():
                        if symbol in symbols_list:
                            found_sector = sec
                            break
                except Exception as import_err:
                    print(f"  -> Warning: failed to load SECTORS from edge_types: {import_err}")
                
                sector = found_sector if found_sector else 'other'
            
            if sector:
                sector = sector.lower().strip().replace(" ", "")
            
            cursor.execute(
                "UPDATE assets SET market_cap_usd = ?, sector = ? WHERE id = ?",
                (float(mcap), sector, asset_id)
            )
            conn.commit()
            print(f"  -> Updated {symbol}: Mcap = {mcap}, Sector = {sector}")
            time.sleep(0.5) # rate limit
            
        except Exception as e:
            print(f"  -> Failed to fetch {symbol}: {e}")
            
    conn.close()
    print("Database enrichment complete!")

if __name__ == "__main__":
    enrich_assets()
