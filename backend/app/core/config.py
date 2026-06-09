from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    groq_api_key: str
    langchain_api_key: str
    langchain_tracing_v2: str = "true"
    langchain_project: str = "stgcn-crypto"
    sentry_dsn: str
    model_artifact_path: str = "./artifacts/best_model.pt"
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
        protected_namespaces = ()

settings = Settings()
