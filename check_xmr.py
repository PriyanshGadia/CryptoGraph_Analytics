import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect("backend/cryptograph.db")
days = 30
since = datetime.now(timezone.utc) - timedelta(days=days)
print("since:", since.isoformat())

# Fetch technical_features
query = """
    SELECT asset_id, timestamp, returns_1d
    FROM technical_features
    WHERE timestamp >= ?
"""
rows = conn.execute(query, (since.isoformat(),)).fetchall()
print("Total rows in range:", len(rows))

if rows:
    df = pd.DataFrame(rows, columns=["asset_id", "timestamp", "returns_1d"])
    df["date"] = df["timestamp"].apply(lambda x: str(x).split("T")[0] if isinstance(x, str) else str(x)[:10])
    
    # Pivot
    pivot = df.pivot_table(index="date", columns="asset_id", values="returns_1d")
    print("Pivot shape before dropna:", pivot.shape)
    pivot_ffill = pivot.ffill()
    min_periods = max(1, int(len(pivot_ffill) * 0.5))
    pivot_dropped = pivot_ffill.dropna(axis=1, thresh=min_periods)
    print("Pivot shape after dropna:", pivot_dropped.shape)
    
    # Let's see which assets were dropped
    all_assets_query = "SELECT id, symbol FROM assets"
    assets = conn.execute(all_assets_query).fetchall()
    asset_map = {a[0]: a[1] for a in assets}
    
    remaining_symbols = [asset_map.get(aid, str(aid)) for aid in pivot_dropped.columns]
    dropped_symbols = [asset_map.get(aid, str(aid)) for aid in asset_map if aid not in pivot_dropped.columns]
    print("Remaining symbols count:", len(remaining_symbols))
    print("Dropped symbols:", dropped_symbols)
    
    # Check if returns_1d are all 0 or empty for these 30 days
    non_zero_rows = df[df["returns_1d"] != 0.0]
    print("Non-zero returns rows count in last 30 days:", len(non_zero_rows))
    print("Sample non-zero returns:", non_zero_rows.head(5))
    
    # Calculate correlations
    corr_matrix = pivot_dropped.corr(method="pearson").fillna(0.0)
    print("Correlation matrix description:")
    print(corr_matrix.describe())
