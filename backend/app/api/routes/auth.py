from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import hmac
from app.core.config import get_setting
from app.core.security import create_jwt_token

router = APIRouter(prefix="/auth", tags=["auth"])

class TokenRequest(BaseModel):
    username: str = Field("admin", max_length=50)
    api_key: str = Field(..., max_length=256)

@router.post("/token")
def login_for_access_token(payload: TokenRequest):
    """
    Issues a short-lived signed JWT session token if the provided API key is valid.
    Enables single-user dashboard session state without raw API key retention.
    """
    configured_key = get_setting("api_key")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System authentication is not initialized."
        )

    # Constant time credential comparison
    if not hmac.compare_digest(payload.api_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API key credentials."
        )

    # Generate 1-hour valid token
    access_token = create_jwt_token(
        payload={"sub": payload.username, "role": "admin"},
        expires_in=3600
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600
    }
