import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force testing environment configuration before imports
os.environ["TESTING"] = "True"

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
if str(root_dir / "backend") not in sys.path:
    sys.path.append(str(root_dir / "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal
from app.db.models import Asset, Prediction, AppSetting, OHLCV

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_explain_fallback_system_xai(client):
    # Ensure there is no groq_api_key in DB during fallback test
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter(AppSetting.setting_key == "groq_api_key").first()
        if setting:
            db.delete(setting)
            db.commit()
    finally:
        db.close()

    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    
    # Request explain for seeded asset
    response = client.get("/api/v1/explain/DYDX", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "DYDX"
    assert "explanation" in data
    assert "top_features" in data
    assert isinstance(data["top_features"], dict)

@patch("app.api.routes.explain.Groq")
def test_explain_llm_path(mock_groq_class, client):
    # Insert a dummy groq_api_key setting in DB
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter(AppSetting.setting_key == "groq_api_key").first()
        if not setting:
            setting = AppSetting(setting_key="groq_api_key", setting_value="encrypted_fake_key")
            db.add(setting)
            db.commit()
            
        # Mock decrypt_secret to return the decrypted fake key
        with patch("app.api.routes.explain.decrypt_secret", return_value="fake_groq_key"):
            # Mock the Groq client
            mock_client = MagicMock()
            mock_completion = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "This is a mocked LLM explanation of the GNN signal."
            mock_completion.choices = [MagicMock(message=mock_message)]
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_class.return_value = mock_client

            from app.core.config import get_setting
            api_key = get_setting("api_key") or os.getenv("API_KEY")
            headers = {"X-API-Key": api_key} if api_key else {}

            response = client.get("/api/v1/explain/DYDX", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "mocked LLM explanation" in data["explanation"]
    finally:
        # Clean up setting
        setting = db.query(AppSetting).filter(AppSetting.setting_key == "groq_api_key").first()
        if setting:
            db.delete(setting)
            db.commit()
        db.close()

def test_backtest_endpoint_validation(client):
    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    # Test invalid date range
    payload = {
        "symbol": "DYDX",
        "start_date": "2026-13-45",
        "end_date": "2026-07-08",
        "model_version": "stgcn-v1.0"
    }
    response = client.post("/api/v1/backtest", json=payload, headers=headers)
    assert response.status_code == 422
    assert "Date must be in YYYY-MM-DD format" in response.json()["detail"][0]["msg"]

def test_backtest_endpoint_success(client):
    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    # Run backtest on seeded DYDX data range
    payload = {
        "symbol": "DYDX",
        "start_date": "2026-06-01",
        "end_date": "2026-07-08",
        "model_version": "stgcn-v1.0"
    }
    response = client.post("/api/v1/backtest", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["symbol"] == "DYDX"
    assert "metrics" in data
    assert "sharpe_ratio" in data["metrics"]

def test_jwt_auth_flow(client):
    from app.core.config import get_setting
    api_key = get_setting("api_key") or os.getenv("API_KEY")
    
    # 1. Request token with correct api key
    payload = {
        "username": "test_user",
        "api_key": api_key
    }
    response = client.post("/api/v1/auth/token", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # 2. Use JWT token to request a secure endpoint (e.g. predictions)
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/predictions?limit=5", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # 3. Verify that sending incorrect credentials returns 401
    payload_bad = {
        "username": "test_user",
        "api_key": "wrong_key_here"
    }
    response = client.post("/api/v1/auth/token", json=payload_bad)
    assert response.status_code == 401
