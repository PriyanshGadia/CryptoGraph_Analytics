from supabase import create_client, Client
from app.core.config import settings

# Singleton initialized at import time using SERVICE_ROLE_KEY
supabase: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)
