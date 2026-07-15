import sys
import os

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

from app.db.database import SessionLocal
from app.db.models import Prediction, Asset

db = SessionLocal()
try:
    asset = db.query(Asset).filter(Asset.symbol == 'ETH').first()
    if asset:
        preds = db.query(Prediction).filter(Prediction.asset_id == asset.id).order_by(Prediction.predicted_at.desc()).limit(5).all()
        for p in preds:
            print(f"Predicted At: {p.predicted_at}")
            print(f"  Direction: {p.direction}")
            print(f"  Confidence: {p.confidence}")
            print(f"  t_shap_attributions: {p.t_shap_attributions}")
    else:
        print("ETH asset not found.")
finally:
    db.close()
