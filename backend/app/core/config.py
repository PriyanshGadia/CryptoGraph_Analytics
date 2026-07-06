"""
Application configuration module.

Settings priority:
1. app_settings SQLite table (user-configured via UI)
2. .env file (developer fallback)
3. Hardcoded defaults

The get_setting() function provides a unified way to fetch any setting
from the app_settings table first, falling back to pydantic-settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    langchain_api_key: Optional[str] = None
    langchain_tracing_v2: str = "true"
    langchain_project: str = "stgcn-crypto"
    sentry_dsn: Optional[str] = None
    model_artifact_path: str = "./artifacts/best_model.pt"
    environment: str = "development"
    api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
        protected_namespaces = ()

settings = Settings()


def get_setting(key: str, default: str = None) -> Optional[str]:
    """
    Fetches a setting value with DB-first priority:
    1. Checks the app_settings SQLite table (user-configured via Settings page)
    2. Falls back to the pydantic Settings object (.env / defaults)
    
    This ensures API keys saved through the UI are actually used.
    """
    try:
        from app.db.database import SessionLocal
        from app.db.models_sqla import AppSetting
        from app.core.security import decrypt_secret

        db = SessionLocal()
        try:
            record = db.query(AppSetting).filter(AppSetting.setting_key == key).first()
            if record and record.setting_value:
                value = decrypt_secret(record.setting_value)
                if value:
                    return value
        finally:
            db.close()
    except Exception:
        pass

    # Fallback to pydantic settings
    env_val = getattr(settings, key, None)
    if env_val:
        return env_val

    return default

# Initialize LangSmith tracing securely on configuration load
import os
os.environ["LANGCHAIN_TRACING_V2"] = settings.langchain_tracing_v2
if getattr(settings, 'langchain_api_key', None):
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
