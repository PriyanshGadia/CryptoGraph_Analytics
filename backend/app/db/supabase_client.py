from supabase import create_client, Client
from app.core.config import settings

# Singleton initialized at import time using SERVICE_ROLE_KEY
supabase: Client | None = None
if settings.supabase_url and settings.supabase_service_role_key:
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    except Exception as e:
        print(f"Warning: Failed to initialize Supabase client: {e}")
else:
    print("Warning: Supabase keys not found in settings. Running in local-only fallback mode.")
