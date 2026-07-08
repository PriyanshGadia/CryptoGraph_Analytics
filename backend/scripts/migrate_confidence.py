import sys
import os
from sqlalchemy import create_engine, text

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(backend_dir)

from app.db.database import SQLALCHEMY_DATABASE_URL

def migrate():
    print("Starting confidence scale migration...")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    with engine.begin() as conn:
        # Check current count of problematic rows
        result = conn.execute(text("SELECT COUNT(*) FROM predictions WHERE confidence > 1.0;")).scalar()
        print(f"Found {result} predictions with confidence > 1.0")
        
        if result > 0:
            # Execute migration
            conn.execute(text("UPDATE predictions SET confidence = confidence / 100.0 WHERE confidence > 1.0;"))
            print(f"Successfully migrated {result} rows to [0.0, 1.0] scale.")
        else:
            print("No rows need migration.")
            
if __name__ == "__main__":
    migrate()
