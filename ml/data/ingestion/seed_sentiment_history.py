"""
Seeds historical sentiment_score, community_score, public_interest
for all assets using the existing fear_greed values as a base signal.
"""
import os, random
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).parent.parent.parent / ".env")
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

SENTIMENT_BIAS = {
    "BTC": 0.15, "ETH": 0.12, "SOL": 0.10, "BNB": 0.08,
    "ADA": 0.05, "AVAX": 0.07, "LINK": 0.06, "DOT": 0.05,
    "DOGE": 0.20,
}
DEFAULT_BIAS = 0.02

def seed_sentiment_history():
    assets = supabase.table("assets").select("id,symbol").execute().data

    for asset in assets:
        asset_id = asset["id"]
        symbol   = asset["symbol"]
        bias     = SENTIMENT_BIAS.get(symbol, DEFAULT_BIAS)

        all_rows = []
        offset = 0
        while True:
            res = (supabase.table("sentiment")
                .select("id,timestamp,fear_greed,sentiment_score")
                .eq("asset_id", asset_id)
                .is_("sentiment_score", "null")
                .not_.is_("fear_greed", "null")
                .range(offset, offset + 999)
                .execute())
            if not res.data:
                break
            all_rows.extend(res.data)
            if len(res.data) < 1000:
                break
            offset += 1000

        if not all_rows:
            print(f"No null sentiment rows for {symbol}")
            continue

        records = []
        prev_score = bias

        for row in all_rows:
            fg = row["fear_greed"]
            if fg is None:
                continue

            fg_signal = (fg / 100.0) * 2 - 1
            noise = random.gauss(0, 0.05)
            score = 0.7 * prev_score + 0.2 * fg_signal + 0.1 * bias + noise
            score = max(-1.0, min(1.0, score))
            prev_score = score

            community = max(0, min(100, fg * 0.6 + random.gauss(20, 5)))
            public_interest = max(0, min(100, fg * 0.4 + random.gauss(15, 8)))

            records.append({
                "id": row["id"],
                "asset_id": asset_id,
                "timestamp": row["timestamp"],
                "sentiment_score":  round(score, 6),
                "community_score":  round(community, 4),
                "public_interest":  round(public_interest, 4),
                "news_volume":      0
            })

        for i in range(0, len(records), 500):
            batch = records[i:i+500]
            supabase.table("sentiment").upsert(
                batch, on_conflict="asset_id,timestamp"
            ).execute()

        print(f"Seeded {len(records)} sentiment rows for {symbol}")

    print("Sentiment history seeding complete")

if __name__ == "__main__":
    seed_sentiment_history()
