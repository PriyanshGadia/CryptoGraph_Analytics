
from fastapi.testclient import TestClient
import sys
sys.path.append('backend')
from app.main import app
client = TestClient(app)
response = client.get('/api/coins/BTC/ohlcv?period=1M')
print(response.status_code)
print(response.json()[:2])

