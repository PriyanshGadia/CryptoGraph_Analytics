
import sqlite3
import yfinance as yf

# Static Sector Map matching Screener UI categories
SECTOR_MAP = {
    'BTC': 'payment', 'ETH': 'layer1', 'BNB': 'exchange', 'SOL': 'layer1', 'XRP': 'payment',
    'ADA': 'layer1', 'DOGE': 'payment', 'AVAX': 'layer1', 'LINK': 'defi', 'DOT': 'layer1',
    'POL': 'layer1', 'UNI': 'defi', 'LTC': 'payment', 'BCH': 'payment', 'XLM': 'payment',
    'ALGO': 'layer1', 'VET': 'other', 'FIL': 'storage', 'TRX': 'layer1', 'NEAR': 'layer1',
    'SAND': 'gaming', 'MANA': 'gaming', 'AXS': 'gaming', 'THETA': 'other', 'XMR': 'privacy',
    'EOS': 'layer1', 'AAVE': 'defi', 'MKR': 'defi', 'COMP': 'defi', 'SNX': 'defi',
    'YFI': 'defi', 'SUSHI': 'defi', 'CRV': 'defi', 'BAL': 'defi', 'ZRX': 'defi',
    'LRC': 'defi', 'BAT': 'other', 'ZEC': 'privacy', 'DASH': 'payment', 'ICX': 'layer1',
    'QTUM': 'layer1', 'ZIL': 'layer1', '1INCH': 'defi', 'FTM': 'layer1', 'REN': 'defi',
    'WAVES': 'layer1', 'ONT': 'layer1', 'IOTA': 'other', 'DGB': 'payment'
}

conn = sqlite3.connect('backend/cryptograph.db')
assets = conn.execute('SELECT id, symbol FROM assets').fetchall()

updated = 0
for aid, sym in assets:
    sector = SECTOR_MAP.get(sym, 'other')
    
    # Try fetching real market cap from yfinance
    mcap = 0.0
    try:
        info = yf.Ticker(f'{sym}-USD').info
        if 'marketCap' in info and info['marketCap']:
            mcap = float(info['marketCap'])
    except Exception as e:
        pass
        
    conn.execute('UPDATE assets SET sector = ?, market_cap_usd = ? WHERE id = ?', (sector, mcap, aid))
    updated += 1
    print(f'Updated {sym}: Sector={sector}, MCap=')

conn.commit()
conn.close()
print(f'Updated {updated} assets.')

