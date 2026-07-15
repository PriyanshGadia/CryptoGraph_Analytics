import sqlite3

conn = sqlite3.connect('G:\\Programming\\CryptoGraph_Analytics\\backend\\cryptograph.db')
cursor = conn.cursor()

cursor.execute("SELECT asset_id, direction, confidence, confidence_interval_lower, confidence_interval_upper, predicted_at FROM predictions ORDER BY predicted_at DESC LIMIT 20")
rows = cursor.fetchall()
print("Latest Predictions:")
for r in rows:
    print(r)

conn.close()
