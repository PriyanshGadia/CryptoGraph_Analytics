import sys
import os
import traceback

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

from app.db.database import SessionLocal
from app.api.routes.risk import get_macro_data

db = SessionLocal()
try:
    print("Calling get_macro_data...")
    res = get_macro_data(db)
    with open('macro_result.txt', 'w') as f:
        f.write(f"SUCCESS: {res}\n")
    print("Saved success.")
except Exception as e:
    with open('macro_result.txt', 'w') as f:
        f.write(f"ERROR: {str(e)}\n{traceback.format_exc()}\n")
    print("Saved error.")
finally:
    db.close()
