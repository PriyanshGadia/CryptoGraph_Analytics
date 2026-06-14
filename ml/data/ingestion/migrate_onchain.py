import sqlite3
from pathlib import Path
from datetime import datetime, timezone

_DB_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent.parent / "backend" / "cryptograph.db",
    Path(__file__).resolve().parent.parent.parent.parent / "cryptograph.db",
]
DB_PATH = next((p for p in _DB_CANDIDATES if p.exists()), _DB_CANDIDATES[0])

def migrate_onchain():
    print(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("Creating onchain_metrics table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS onchain_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            tvl REAL DEFAULT 0.0,
            revenue REAL DEFAULT 0.0,
            active_users REAL DEFAULT 0.0,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(asset_id, timestamp)
        )
    """)
    conn.commit()

    print("Padding historical OHLCV dates with zeroes in onchain_metrics...")
    # Insert 0.0 for all (asset_id, timestamp) combinations in OHLCV
    # that don't already exist in onchain_metrics.
    cursor.execute("""
        INSERT OR IGNORE INTO onchain_metrics (asset_id, timestamp, tvl, revenue, active_users)
        SELECT asset_id, timestamp, 0.0, 0.0, 0.0
        FROM ohlcv
    """)
    inserted = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"Migration complete. Padded {inserted} records.")

if __name__ == "__main__":
    migrate_onchain()
