import os
import sys
import sqlite3

db_path = 'G:\\Programming\\CryptoGraph_Analytics\\backend\\cryptograph.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get list of tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables in DB: {tables}")

for table in ['macro_indicators', 'app_settings', 'assets']:
    if table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        print(f"\nSchema for {table}:")
        for col in cursor.fetchall():
            print(f"  {col[1]} ({col[2]})")
        
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"  Row count: {count}")
        
        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
            print("  Sample rows:")
            for row in cursor.fetchall():
                print(f"    {row}")
    else:
        print(f"\nTable {table} does not exist.")

conn.close()
