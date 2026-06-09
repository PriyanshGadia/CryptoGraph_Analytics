"""API Security and Authentication."""

from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)) -> bool:
    """
    Verify API key for protected routes.
    Placeholder for development that always returns True.
    """
    return True
