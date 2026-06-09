from app.db.supabase_client import supabase

def get_supabase():
    """FastAPI dependency returning the Supabase client."""
    return supabase
