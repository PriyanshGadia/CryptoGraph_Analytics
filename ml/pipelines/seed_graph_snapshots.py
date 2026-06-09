"""
Seeds graph_snapshots table so the Network Graph page shows all 50 nodes.
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

SECTORS = {
    "layer1":   ["BTC","ETH","SOL","ADA","AVAX","DOT","NEAR","FTM"],
    "defi":     ["UNI","AAVE","MKR","COMP","CRV","SUSHI","BAL","YFI","SNX"],
    "exchange": ["BNB","ZRX","LRC"],
    "payment":  ["XRP","XLM","LTC","BCH","DASH","XMR"],
    "gaming":   ["SAND","MANA","AXS","THETA"],
    "privacy":  ["XMR","ZEC","DASH"],
    "storage":  ["FIL","IOTA"],
    "other":    ["DOGE","LINK","ATOM","VET","TRX","ALGO","EOS","WAVES",
                 "ICX","QTUM","ONT","ZIL","DGB","1INCH","BAT","REN","MATIC"]
}

def seed_graph():
    assets = supabase.table("assets").select("id, symbol").execute().data
    symbol_to_id = {a["symbol"]: a["id"] for a in assets}
    now = datetime.now(timezone.utc)
    records = []

    for sector, symbols in SECTORS.items():
        valid = [s for s in symbols if s in symbol_to_id]
        for i in range(len(valid)):
            for j in range(i+1, len(valid)):
                src, tgt = valid[i], valid[j]
                weight = round(random.uniform(0.6, 1.0), 4)
                records.append({
                    "timestamp":    now.isoformat(),
                    "source_asset": symbol_to_id[src],
                    "target_asset": symbol_to_id[tgt],
                    "weight":       weight,
                    "edge_type":    "sector"
                })
                records.append({
                    "timestamp":    now.isoformat(),
                    "source_asset": symbol_to_id[tgt],
                    "target_asset": symbol_to_id[src],
                    "weight":       weight,
                    "edge_type":    "sector"
                })

    correlated_pairs = [
        ("BTC","ETH",0.92), ("BTC","SOL",0.78), ("ETH","SOL",0.81),
        ("BTC","AVAX",0.72), ("ETH","LINK",0.75), ("BNB","ETH",0.71),
        ("ADA","DOT",0.73), ("UNI","AAVE",0.77),
        ("SOL","NEAR",0.74), ("BTC","XRP",0.65), ("ETH","MATIC",0.76),
    ]
    for src, tgt, w in correlated_pairs:
        if src in symbol_to_id and tgt in symbol_to_id:
            for s, t in [(src,tgt),(tgt,src)]:
                records.append({
                    "timestamp":    now.isoformat(),
                    "source_asset": symbol_to_id[s],
                    "target_asset": symbol_to_id[t],
                    "weight":       w,
                    "edge_type":    "correlation"
                })

    batch_size = 500
    for i in range(0, len(records), batch_size):
        supabase.table("graph_snapshots").insert(records[i:i+batch_size]).execute()

    print(f"Seeded {len(records)} graph edges for {len(assets)} assets")

if __name__ == "__main__":
    seed_graph()
