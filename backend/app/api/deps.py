from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.db.supabase_client import supabase
from app.db.database import SessionLocal
from app.core.config import get_setting, settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_supabase():
    """FastAPI dependency returning the Supabase client."""
    return supabase

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
    configured_key = get_setting("api_key") or getattr(settings, "api_key", None)
    
    if not configured_key:
        # If no key is configured in production, main.py fails closed.
        # But if we reach here without a key configured, it means we're
        # in a mode that demands it but it's not set. Fail closed.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
        
    if not api_key or api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    return api_key
