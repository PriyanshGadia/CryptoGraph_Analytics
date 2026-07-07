import hmac
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.websockets import WebSocket

from app.db.database import SessionLocal
from app.core.config import get_setting, settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_db():
    """FastAPI dependency yielding a SQLAlchemy DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_settings():
    """FastAPI dependency returning application settings."""
    return settings

def verify_api_key(api_key: str = Security(api_key_header)):
    """
    FastAPI dependency that enforces API key authentication.
    Requires X-API-Key header to match the configured API key.
    """
    configured_key = get_setting("api_key")
    
    if not configured_key:
        # If no key is configured in production, main.py fails closed.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
        
    if not api_key or not hmac.compare_digest(api_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    return api_key

async def verify_ws_api_key(websocket: WebSocket) -> bool:
    """
    Validates API key for WebSocket connections using query parameters or headers.
    """
    api_key = websocket.query_params.get("api_key") or websocket.headers.get("X-API-Key")
    configured_key = get_setting("api_key")
    
    if not configured_key or not api_key or not hmac.compare_digest(api_key.encode("utf-8"), configured_key.encode("utf-8")):
        return False
    return True

