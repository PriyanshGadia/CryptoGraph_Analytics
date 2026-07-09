from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.deps import verify_api_key
from app.db.models import AppSetting
from app.core.security import encrypt_secret, decrypt_secret
from pydantic import BaseModel, field_validator
from typing import Dict, Optional

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(verify_api_key)])

SENSITIVE_KEYWORDS = ["key", "secret", "dsn", "password", "token"]

def _is_sensitive(key: str) -> bool:
    return any(kw in key.lower() for kw in SENSITIVE_KEYWORDS)

def _mask_value(value: str) -> str:
    """Returns a masked version of a sensitive value for display purposes."""
    if not value or len(value) < 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]


class SettingsUpdate(BaseModel):
    settings: Dict[str, str]

    @field_validator("settings")
    @classmethod
    def validate_settings_keys(cls, v: Dict[str, str]) -> Dict[str, str]:
        ALLOWED_KEYS = ["groq_api_key"]
        for key, val in v.items():
            if key not in ALLOWED_KEYS:
                raise ValueError(f"Setting key '{key}' is not allowed.")
            if key == "groq_api_key" and val and len(val.strip()) < 10:
                raise ValueError("Groq API key must be at least 10 characters long.")
        return v

class SettingsResponse(BaseModel):
    values: Dict[str, Optional[str]]
    configured: Dict[str, bool]

@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """
    Retrieve all app settings.
    For sensitive keys: returns masked values + a 'configured' boolean.
    For non-sensitive keys: returns the actual value.
    """
    settings_records = db.query(AppSetting).all()
    
    values = {}
    configured = {}
    
    ALLOWED_KEYS = ["groq_api_key"]
    
    for record in settings_records:
        key = record.setting_key
        if key not in ALLOWED_KEYS:
            continue
            
        raw_value = record.setting_value or ""
        
        if _is_sensitive(key):
            # Decrypt to check if it's actually configured
            decrypted = decrypt_secret(raw_value)
            has_value = bool(decrypted and decrypted.strip())
            configured[key] = has_value
            # Return None — frontend should show placeholder
            values[key] = None
        else:
            values[key] = raw_value
            configured[key] = bool(raw_value)
    
    return {"values": values, "configured": configured}

@router.post("")
def update_settings(update_data: SettingsUpdate, db: Session = Depends(get_db)):
    """
    Update or create app settings (Batched to prevent N+1 queries).
    Skips empty strings for sensitive fields (user didn't change them).
    """
    # Fetch all existing records that match the keys we are updating
    ALLOWED_KEYS = ["groq_api_key"]
    keys_to_update = [k for k in update_data.settings.keys() if k in ALLOWED_KEYS]
    
    if not keys_to_update:
        return {"status": "success", "message": "Updated 0 setting(s)"}
        
    existing_records = db.query(AppSetting).filter(AppSetting.setting_key.in_(keys_to_update)).all()
    
    # Create a lookup dictionary
    existing_lookup = {record.setting_key: record for record in existing_records}
    
    updated_count = 0
    
    for key in keys_to_update:
        value = update_data.settings.get(key, "")
        is_sensitive = _is_sensitive(key)
        
        # Skip empty sensitive fields — user didn't change them
        if is_sensitive and (not value or not value.strip()):
            continue
        
        # Encrypt sensitive values
        final_value = encrypt_secret(value) if is_sensitive else value
        
        if key in existing_lookup:
            existing_lookup[key].setting_value = final_value
        else:
            new_setting = AppSetting(setting_key=key, setting_value=final_value)
            db.add(new_setting)
        updated_count += 1
            
    db.commit()
    return {"status": "success", "message": f"Updated {updated_count} setting(s)"}
