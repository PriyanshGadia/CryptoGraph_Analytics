"""
Supabase Cloud Synchronization.
Provides a graceful fallback cloud replication layer for multi-tenant SaaS.
If Supabase keys are missing, the system gracefully degrades to local SQLite.
"""

import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.db.models_sqla import AppSetting
from app.core.security import decrypt_secret

class SupabaseSyncManager:
    def __init__(self, db: Session):
        self.db = db
        # Fetch keys from SQLite
        url_record = db.query(AppSetting).filter(AppSetting.setting_key == "supabase_url").first()
        key_record = db.query(AppSetting).filter(AppSetting.setting_key == "supabase_service_role_key").first()
        
        self.url = url_record.setting_value if url_record else None
        self.key = decrypt_secret(key_record.setting_value) if key_record else None
        
        self.is_enabled = bool(self.url and self.key)

    async def sync_trade_history(self, trades: List[Dict[str, Any]]):
        """Pushes trade history to the Supabase cloud."""
        if not self.is_enabled:
            return # Graceful fallback to local-only
            
        endpoint = f"{self.url}/rest/v1/trade_history"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=trades, headers=headers)
                if response.status_code not in (200, 201):
                    print(f"[SupabaseSync] Failed to sync trades: {response.text}")
                else:
                    print(f"[SupabaseSync] Synced {len(trades)} trades to cloud.")
        except Exception as e:
            print(f"[SupabaseSync] Sync error: {e}")

    async def sync_portfolio_state(self, state: Dict[str, Any]):
        """Pushes the portfolio state to the cloud for multi-tenant dashboard rendering."""
        if not self.is_enabled:
            return
            
        endpoint = f"{self.url}/rest/v1/portfolio_state"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=state, headers=headers)
                if response.status_code not in (200, 201):
                    print(f"[SupabaseSync] Failed to sync portfolio: {response.text}")
        except Exception as e:
            print(f"[SupabaseSync] Sync error: {e}")

