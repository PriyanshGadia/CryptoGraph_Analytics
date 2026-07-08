import sqlite3
import yfinance as yf
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def fetch_asset_info(yf_symbol: str) -> dict:
    ticker = yf.Ticker(yf_symbol)
    return ticker.info

def enrich_assets():
    print("Connecting to database...")
    conn = sqlite3.connect('cryptograph.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, symbol FROM assets")
    assets = cursor.fetchall()
    
    print(f"Found {len(assets)} assets. Fetching data from yfinance...")
    
    for asset_id, symbol in assets:
        yf_symbol = f"{symbol}-USD"
        print(f"Fetching {yf_symbol}...")
        try:
            info = fetch_asset_info(yf_symbol)
            
            mcap = info.get("marketCap", 0.0)
            if not mcap:
                # Some cryptos don't have marketCap in info, fallback to previousClose * circulatingSupply if available
                circ_supply = info.get("circulatingSupply", 0.0)
                price = info.get("previousClose", 0.0)
                mcap = circ_supply * price
                
            # Sector for crypto is usually missing or "Cryptocurrency". 
            # We can map some known ones or use what Yahoo provides.
            sector = info.get("sector", None)
            category = info.get("category", None)
            
            # Map sectors logically if missing
            if not sector or sector == 'Cryptocurrency':
                if symbol in ['BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'NEAR', 'APT', 'SUI', 'SEI', 'ICP', 'EGLD', 'ALGO', 'MINA', 'INJ', 'FTM']:
                    sector = 'Layer 1'
                elif symbol in ['OP', 'ARB', 'MATIC', 'IMX', 'MNT']:
                    sector = 'Layer 2'
                elif symbol in ['UNI', 'AAVE', 'MKR', 'SNX', 'CRV', 'DYDX', 'RUNE', 'LDO']:
                    sector = 'DeFi'
                elif symbol in ['AXS', 'SAND', 'MANA', 'GALA', 'ILV']:
                    sector = 'Gaming'
                elif symbol in ['LINK', 'GRT', 'PYTH', 'QNT']:
                    sector = 'Infrastructure'
                elif symbol in ['DOGE', 'SHIB', 'PEPE', 'WIF', 'BONK']:
                    sector = 'Meme'
                else:
                    sector = 'Other'
            
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
