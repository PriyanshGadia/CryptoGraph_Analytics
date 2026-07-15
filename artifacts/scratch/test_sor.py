import sys
import os

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

os.environ["TRADING_MODE"] = "paper"

from app.services.smart_order_router import SmartOrderRouter

sor = SmartOrderRouter()
for sym in ["BTC", "ETH", "SOL"]:
    try:
        route = sor.calculate_best_route(sym, "buy", 10000.0, 3000.0 if sym == "ETH" else 60000.0 if sym == "BTC" else 140.0)
        print(f"Symbol: {sym}, Route: {route}")
    except Exception as e:
        print(f"Error for {sym}: {e}")
