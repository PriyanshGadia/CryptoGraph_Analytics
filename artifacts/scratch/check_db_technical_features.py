import sys
import os

sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics'))
sys.path.insert(0, os.path.abspath('G:\\Programming\\CryptoGraph_Analytics\\backend'))

from app.db.database import SessionLocal
from app.db.models import TechnicalFeature, Asset

db = SessionLocal()
try:
    asset = db.query(Asset).filter(Asset.symbol == 'ETH').first()
    if asset:
        row = db.query(TechnicalFeature).filter(TechnicalFeature.asset_id == asset.id).order_by(TechnicalFeature.timestamp.desc()).first()
        if row:
            print("Latest Technical Features for ETH:")
            print(f"  Timestamp: {row.timestamp}")
            print(f"  RSI(14): {row.rsi_14}")
            print(f"  MACD: {row.macd}")
            print(f"  MACD Signal: {row.macd_signal}")
            print(f"  Returns 1D: {row.returns_1d}")
            print(f"  Returns 7D: {row.returns_7d}")
            print(f"  Volatility 7D: {row.volatility_7d}")
        else:
            print("No technical features found for ETH.")
    else:
        print("ETH asset not found.")
finally:
    db.close()
