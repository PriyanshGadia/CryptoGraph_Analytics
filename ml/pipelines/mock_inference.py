"""
Seeds predictions table with realistic mock data for all 50 assets.
Run this once to populate the dashboard while the real model trains.
"""
import os, random
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).parent.parent / ".env")

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

DIRECTIONS = ["strong_up", "up", "neutral", "down", "strong_down"]
VOLATILITY  = ["low", "medium", "high", "extreme"]
DIRECTION_WEIGHTS = [0.15, 0.30, 0.25, 0.20, 0.10]

def seed_predictions():
    assets = supabase.table("assets").select("id, symbol").execute().data
    if not assets:
        print("No assets found. Run binance_collector.py first.")
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

        records.append({
            "asset_id":          asset["id"],
            "timestamp":         now.isoformat(),
            "predicted_at":      now.isoformat(),
            "direction":         direction,
            "confidence":        confidence,
            "volatility_regime": volatility,
            "shap_values":       shap_values,
            "model_version":     "mock-v0.1"
        })

    # Delete any existing mock predictions first
    supabase.table("predictions").delete().eq(
        "model_version", "mock-v0.1"
    ).execute()

    supabase.table("predictions").insert(records).execute()

    print(f"Seeded {len(records)} predictions for {len(assets)} assets")
    print("Refresh your dashboard at http://localhost:3000")

if __name__ == "__main__":
    seed_predictions()
