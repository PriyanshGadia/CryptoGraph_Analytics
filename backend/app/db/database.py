from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from pathlib import Path

# Local SQLite connection string - explicitly point to backend/cryptograph.db
base_dir = Path(__file__).resolve().parent.parent.parent
db_path = base_dir / "cryptograph.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

# Setting check_same_thread=False is needed for SQLite in FastAPI/multi-thread envs
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0  # 30 seconds busy timeout for massive concurrent writes
    }
)

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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI dependency for yielding a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
