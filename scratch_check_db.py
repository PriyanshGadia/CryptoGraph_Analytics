import sqlite3, os
for p in ['backend/cryptograph.db', 'cryptograph.db']:
    if os.path.exists(p):
        print(f"\n=== {p} ({os.path.getsize(p)} bytes) ===")
        conn = sqlite3.connect(p, timeout=10)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        print("Tables:", tables)
        for t in ['assets', 'technical_features', 'ohlcv', 'forecasts', 'predictions', 'sentiment', 'macro_indicators']:
            if t in tables:
                c.execute(f"SELECT COUNT(*) FROM [{t}]")
                print(f"  {t}: {c.fetchone()[0]} rows")
        if 'assets' in tables:
            c.execute("SELECT symbol FROM assets LIMIT 10")
            print("  symbols:", [r[0] for r in c.fetchall()])
        conn.close()
    else:
        print(f"{p}: NOT FOUND")
