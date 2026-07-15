from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from pathlib import Path

# Local connection string - allow override via DATABASE_URL
db_url_env = os.getenv("DATABASE_URL")
if db_url_env:
    # Handle Heroku/Supabase style postgres:// URLs
    if db_url_env.startswith("postgres://"):
        db_url_env = db_url_env.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url_env.startswith("postgresql://"):
        db_url_env = db_url_env.replace("postgresql://", "postgresql+psycopg2://", 1)
    SQLALCHEMY_DATABASE_URL = db_url_env
else:
    db_path_env = os.getenv("DATABASE_PATH")
    if db_path_env:
        SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path_env}"
    else:
        base_dir = Path(__file__).resolve().parent.parent.parent
        db_path = base_dir / "cryptograph.db"
        SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

from sqlalchemy.pool import NullPool

# Configure connection arguments and engine events dynamically depending on active database dialect
is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

connect_args = {}
if is_sqlite:
    # Setting check_same_thread=False is needed for SQLite in FastAPI/multi-thread envs
    connect_args = {
        "check_same_thread": False,
        "timeout": 30.0  # 30 seconds busy timeout for massive concurrent writes
    }

def custom_json_serializer(obj):
    import json
    def default(o):
        try:
            import numpy as np
            if isinstance(o, (np.integer, np.floating)):
                return o.item()
            if isinstance(o, np.ndarray):
                return o.tolist()
        except ImportError:
            pass
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
    return json.dumps(obj, default=default)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args=connect_args,
    poolclass=NullPool,
    json_serializer=custom_json_serializer
)

if is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for high-concurrency writes without locking reads
        cursor.execute("PRAGMA journal_mode=WAL")
        # Set synchronous to NORMAL for faster WAL writes (safe enough for most uses)
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Increase cache size for 20k assets
        cursor.execute("PRAGMA cache_size=-64000") 
        cursor.close()

import time
import sqlite3
from sqlalchemy.exc import OperationalError

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI dependency for yielding a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def execute_with_retry(action_fn, max_retries: int = 5, backoff_seconds: float = 0.2):
    """Executes a database transaction callback with retries on SQLite operational/busy locks."""
    for attempt in range(max_retries):
        try:
            return action_fn()
        except (OperationalError, sqlite3.OperationalError) as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt == max_retries - 1:
                    raise e
                time.sleep(backoff_seconds * (2 ** attempt))
            else:
                raise e
