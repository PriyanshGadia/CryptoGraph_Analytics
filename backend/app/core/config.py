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

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
        protected_namespaces = ()

settings = Settings()
