import sqlite3
conn = sqlite3.connect('backend/cryptograph.db')
conn.execute("UPDATE assets SET symbol = 'POL', name = 'POL' WHERE symbol = 'MATIC'")
conn.commit()
print('Updated MATIC to POL')
