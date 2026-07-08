import pytest
import os
from fastapi.testclient import TestClient

# Set API_KEY for tests so it doesn't fail with 500
os.environ["API_KEY"] = "test_api_key"

from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_health_check():
    """Test the unauthenticated /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "db" in data
    assert "timestamp" in data

def test_protected_routes_unauthorized():
    """Test that missing API keys result in 403 Forbidden."""
    # Attempt to access a protected route without a key
    response = client.get("/api/v1/assets")
    assert response.status_code == 403
    assert "Not authenticated" in response.text or "Could not validate credentials" in response.text

def test_readiness_check():
    """Test the unauthenticated /readiness endpoint."""
    response = client.get("/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "db" in data
    assert "redis" in data


def test_prometheus_metrics_exposed():
    """Test that Prometheus metrics are exposed."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "python_info" in response.text or "http_requests" in response.text
