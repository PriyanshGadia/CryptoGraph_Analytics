import sys
import os

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

from app.db.database import SessionLocal
from app.db.models import Prediction, Asset

db = SessionLocal()
try:
    preds = db.query(Prediction, Asset).join(Asset).order_by(Prediction.predicted_at.desc()).all()
    print(f"Total prediction records: {len(preds)}")
    symbols = [a.symbol for p, a in preds]
    print(f"Unique symbols in predictions: {set(symbols)}")
    print(f"Is 'BTC' in predictions? {'BTC' in symbols}")
    print(f"Is 'ETH' in predictions? {'ETH' in symbols}")
    
    btc_asset = db.query(Asset).filter(Asset.symbol == 'BTC').first()
    eth_asset = db.query(Asset).filter(Asset.symbol == 'ETH').first()
    
    if btc_asset:
        btc_preds = db.query(Prediction).filter(Prediction.asset_id == btc_asset.id).all()
        print(f"BTC has {len(btc_preds)} predictions.")
    if eth_asset:
        eth_preds = db.query(Prediction).filter(Prediction.asset_id == eth_asset.id).all()
        print(f"ETH has {len(eth_preds)} predictions.")
finally:
    db.close()
