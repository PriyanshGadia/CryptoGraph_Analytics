import requests

BASE = "http://localhost:8000"
endpoints = [
    "/api/assets",
    "/api/graph/latest",
    "/api/correlations/matrix?days=30",
    "/api/correlations/sector-average?days=30",
    "/api/sentiment-data/fear-greed-history?days=30",
    "/api/sentiment-data/sector-sentiment",
    "/api/sentiment-data/trending",
    "/api/performance?days=30",
    "/api/risk",
    "/api/risk/macro",
    "/api/portfolio",
    "/api/explain/BTC",
    "/api/predictions?limit=5",
    "/api/screener/?direction=all",
]

for ep in endpoints:
    try:
        r = requests.get(BASE + ep, timeout=15)
        status = r.status_code
        body = r.text[:120] if status != 200 else "OK"
        print(f"[{status}] {ep} -> {body}")
    except Exception as e:
        print(f"[ERR] {ep} -> {e}")
