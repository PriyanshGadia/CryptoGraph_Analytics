import sys
import os

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

from app.db.database import SessionLocal
from app.db.models import Asset

db = SessionLocal()
try:
    assets = db.query(Asset).all()
    print(f"Total assets: {len(assets)}")
    for a in assets:
        print(f"Symbol: {a.symbol}, Name: {a.name}, Sector: {a.sector}")
finally:
    db.close()
