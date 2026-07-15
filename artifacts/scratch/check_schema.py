import sqlite3

conn = sqlite3.connect('G:\\Programming\\CryptoGraph_Analytics\\backend\\cryptograph.db')
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(predictions)")
columns = cursor.fetchall()
for col in columns:
    print(col)

conn.close()
