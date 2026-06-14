from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models_sqla import AppSetting
from app.core.security import encrypt_secret, decrypt_secret
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(prefix="/settings", tags=["settings"])

class SettingsUpdate(BaseModel):
    settings: Dict[str, str]

@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """Retrieve all app settings, decrypting sensitive values."""
    settings_records = db.query(AppSetting).all()
    return {record.setting_key: decrypt_secret(record.setting_value) for record in settings_records}

@router.post("")
def update_settings(update_data: SettingsUpdate, db: Session = Depends(get_db)):
    """Update or create app settings (Batched to prevent N+1 queries)."""
    # Fetch all existing records that match the keys we are updating
    keys_to_update = list(update_data.settings.keys())
    existing_records = db.query(AppSetting).filter(AppSetting.setting_key.in_(keys_to_update)).all()
    
    # Create a lookup dictionary
    existing_lookup = {record.setting_key: record for record in existing_records}
    
    # Update or insert
    for key, value in update_data.settings.items():
        is_sensitive = any(kw in key.lower() for kw in ["key", "secret", "dsn"])
        final_value = encrypt_secret(value) if is_sensitive and value else value
        
        if key in existing_lookup:
            existing_lookup[key].setting_value = final_value
        else:
            new_setting = AppSetting(setting_key=key, setting_value=final_value)
            db.add(new_setting)
            
    db.commit()
    return {"status": "success", "message": "Settings updated"}
