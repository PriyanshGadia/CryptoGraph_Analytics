import os
import sys
import json
from datetime import datetime

# Adjust path to import backend modules
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(root_dir, 'backend'))
sys.path.append(root_dir)

from app.db.database import SessionLocal
from app.api.routes.risk import get_macro_data

def main():
    db = SessionLocal()
    try:
        data = get_macro_data(db)
        print("Macro Data Output:")
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Exception raised: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    main()
