import os
import sys
from sqlalchemy import text

# Adjust path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from app.db.database import SessionLocal

def main():
    db = SessionLocal()
    try:
        # 1. Scale down any rows that are > 1.0
        res = db.execute(text("SELECT COUNT(*) FROM predictions WHERE confidence_interval_lower > 1.0")).scalar()
        print(f"Rows needing scaling update: {res}")
        if res > 0:
            db.execute(text("UPDATE predictions SET confidence_interval_lower = confidence_interval_lower / 100.0, confidence_interval_upper = confidence_interval_upper / 100.0 WHERE confidence_interval_lower > 1.0"))
            db.commit()
            print("Successfully scaled confidence intervals down to 0-1 range.")
        
        # 2. Populate any rows where confidence_interval_lower is NULL
        null_res = db.execute(text("SELECT COUNT(*) FROM predictions WHERE confidence_interval_lower IS NULL")).scalar()
        print(f"Rows with NULL confidence intervals: {null_res}")
        if null_res > 0:
            # For each prediction, compute lower/upper based on its confidence
            db.execute(text("""
                UPDATE predictions 
                SET confidence_interval_lower = MAX(0.0, confidence - 0.05),
                    confidence_interval_upper = MIN(1.0, confidence + 0.05)
                WHERE confidence_interval_lower IS NULL AND confidence IS NOT NULL
            """))
            db.commit()
            print("Successfully populated NULL confidence intervals.")
        else:
            print("No NULL confidence intervals found.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    main()
