
import sqlite3
conn = sqlite3.connect('backend/cryptograph.db')
print(conn.execute('SELECT symbol, timestamp FROM ohlcv JOIN assets ON ohlcv.asset_id = assets.id WHERE symbol=\'BTC\' ORDER BY timestamp DESC LIMIT 1').fetchall())
print(conn.execute('SELECT symbol, timestamp FROM ohlcv JOIN assets ON ohlcv.asset_id = assets.id WHERE symbol=\'REN\' ORDER BY timestamp DESC LIMIT 1').fetchall())

