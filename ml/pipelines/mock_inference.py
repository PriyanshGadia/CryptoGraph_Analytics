"""
Seeds predictions table with realistic mock data for all 50 assets.
Run this once to populate the dashboard while the real model trains.
"""
import os, random, json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "cryptograph.db"

DIRECTIONS = ["strong_up", "up", "neutral", "down", "strong_down"]
VOLATILITY  = ["low", "medium", "high", "extreme"]
DIRECTION_WEIGHTS = [0.15, 0.30, 0.25, 0.20, 0.10]

def seed_predictions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, symbol FROM assets")
    assets = cursor.fetchall()

    if not assets:
        print("No assets found. Run binance_collector.py first.")
        conn.close()
        return

    records = []
    now = datetime.now(timezone.utc)

    # Skip delisted/unavailable symbols that have no price data
    SKIP_SYMBOLS = {"REN", "WAVES", "ONT", "IOTA", "DGB"}

    for asset in assets:
        if asset["symbol"] in SKIP_SYMBOLS:
            continue
        direction  = random.choices(DIRECTIONS, weights=DIRECTION_WEIGHTS, k=1)[0]
        confidence = round(random.uniform(0.55, 0.95), 4)
        volatility = random.choices(
            VOLATILITY,
            weights=[0.3, 0.4, 0.2, 0.1],
            k=1
        )[0]

        shap_values = {
            "rsi_14":          round(random.uniform(-0.3, 0.3), 4),
            "returns_1d":      round(random.uniform(-0.2, 0.2), 4),
            "volatility_7d":   round(random.uniform(-0.15, 0.15), 4),
            "macd":            round(random.uniform(-0.1, 0.1), 4),
            "fear_greed_norm": round(random.uniform(-0.1, 0.1), 4),
        }

        records.append((
            asset["id"],
            now.isoformat(),
            now.isoformat(),
            direction,
            confidence,
            volatility,
            json.dumps(shap_values),
            "mock-v0.1"
        ))

    # Delete any existing mock predictions first
    cursor.execute("DELETE FROM predictions WHERE model_version = 'mock-v0.1'")
    conn.commit()

    # Insert new predictions
    cursor.executemany("""
        INSERT INTO predictions (asset_id, timestamp, predicted_at, direction, confidence, volatility_regime, shap_values, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    conn.commit()

    print(f"Seeded {len(records)} predictions for {len(assets)} assets")
    conn.close()

if __name__ == "__main__":
    seed_predictions()
