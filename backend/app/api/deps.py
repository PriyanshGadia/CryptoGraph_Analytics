import hmac
from fastapi import Security, HTTPException, status, Header
from fastapi.security import APIKeyHeader
from fastapi.websockets import WebSocket

from app.db.database import SessionLocal
from app.core.config import get_setting, settings
from app.core.security import verify_jwt_token

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

def verify_api_key(
    api_key: str = Security(api_key_header),
    authorization: str = Header(None)
):
    """
    FastAPI dependency that enforces API key or JWT token authentication.
    Allows either raw X-API-Key or Bearer <JWT> token inside Authorization header.
    """
    configured_key = get_setting("api_key")
    
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System authentication is not initialized."
        )

    # 1. Try raw X-API-Key authentication
    if api_key and hmac.compare_digest(api_key.encode("utf-8"), configured_key.encode("utf-8")):
        return api_key

    # 2. Try JWT Bearer token authentication
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = verify_jwt_token(token)
        if payload is not None:
            return token

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate credentials"
    )

async def verify_ws_api_key(websocket: WebSocket) -> bool:
    """
    Validates credentials for WebSocket connections using query parameters or headers (API keys or JWT tokens).
    """
    api_key = websocket.query_params.get("api_key") or websocket.headers.get("X-API-Key")
    auth_header = websocket.headers.get("authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif websocket.query_params.get("token"):
        token = websocket.query_params.get("token")
        
    configured_key = get_setting("api_key")
    if not configured_key:
        return False
        
    # Check raw API key
    if api_key and hmac.compare_digest(api_key.encode("utf-8"), configured_key.encode("utf-8")):
        return True
        
    # Check JWT token
    if token:
        payload = verify_jwt_token(token)
        if payload is not None:
            return True
            
    return False


