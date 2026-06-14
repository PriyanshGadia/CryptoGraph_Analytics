
import sqlite3
conn = sqlite3.connect('backend/cryptograph.db')
print(conn.execute('SELECT timestamp FROM ohlcv JOIN assets ON ohlcv.asset_id = assets.id WHERE symbol=\'BTC\' ORDER BY timestamp DESC LIMIT 5').fetchall())

