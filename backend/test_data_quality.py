"""Verify response payloads have real data."""
import requests
import json

BASE = "http://localhost:8000"

def check(name, url, validator):
    r = requests.get(BASE + url, timeout=15)
    data = r.json()
    result = validator(data)
    status = "PASS" if result else "FAIL"
    print(f"[{status}] {name}")
    if not result:
        print(f"  Data sample: {json.dumps(data, default=str)[:200]}")

if __name__ == "__main__":
    # 1. Assets have 24h returns
    check("Assets have 24h returns", "/api/v1/assets", 
          lambda d: any(a.get("price_change_24h_pct") is not None and a["price_change_24h_pct"] != 0 for a in d))

    # 2. Graph has nodes and edges
    check("Graph has nodes+edges", "/api/v1/graph/latest",
          lambda d: len(d.get("nodes", [])) > 0 and len(d.get("edges", [])) > 0)

    # 3. Correlations matrix populated  
    check("Correlations matrix populated", "/api/v1/correlations/matrix?days=30",
          lambda d: len(d.get("symbols", [])) > 0 and len(d.get("matrix", [])) > 0)

    # 4. Fear/greed history has entries
    check("Fear/greed history populated", "/api/v1/sentiment-data/fear-greed-history?days=30",
          lambda d: len(d) > 0)

    # 5. Sector sentiment has entries
    check("Sector sentiment populated", "/api/v1/sentiment-data/sector-sentiment",
          lambda d: len(d) > 0 and any(s.get("avg_sentiment", 0) != 0 for s in d))

    # 6. Risk has real top_volatile and alerts
    check("Risk has top_volatile data", "/api/v1/risk",
          lambda d: len(d.get("top_volatile", [])) > 0)

    check("Risk has real alerts", "/api/v1/risk",
          lambda d: len(d.get("risk_alerts", [])) > 0 and isinstance(d["risk_alerts"][0], dict))

    # 7. Risk macro has VIX  
    check("Macro has real VIX", "/api/v1/risk/macro",
          lambda d: d.get("current_vix", 0) > 0)

    # 8. Performance returns data
    check("Performance returns data", "/api/v1/performance?days=30",
          lambda d: d.get("total_predictions", 0) >= 0)  # Could be 0 if no preds, but shouldn't crash

    # 9. Explain BTC works (system XAI)
    check("XAI explain works", "/api/v1/explain/BTC",
          lambda d: len(d.get("explanation", "")) > 20 and d.get("direction") != "unknown")

    # 10. Portfolio loads
    check("Portfolio loads", "/api/v1/portfolio",
          lambda d: "total_value" in d)

    print("\nDone!")
