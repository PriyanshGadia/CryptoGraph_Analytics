import sys
import os
import pytest
from fastapi.testclient import TestClient

# Adjust sys.path to resolve backend imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from app.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_predictions_endpoint(client):
    import os
    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    response = client.get("/api/v1/predictions?limit=5", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_forecast_endpoint(client):
    import os
    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    # BTC is seeded, so it should exist
    response = client.get("/api/v1/forecast/BTC", headers=headers)
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["symbol"] == "BTC"
    assert "forecast_prices" in json_data
    assert "lower_bound" in json_data
    assert "upper_bound" in json_data
