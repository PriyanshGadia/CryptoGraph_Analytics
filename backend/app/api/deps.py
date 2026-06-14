from app.db.supabase_client import supabase
from app.db.database import SessionLocal

def get_supabase():
    """FastAPI dependency returning the Supabase client."""
    return supabase

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
