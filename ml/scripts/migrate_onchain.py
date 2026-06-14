"""
Migration script to initialize historical on-chain data with zero-padding
if data is missing from DefiLlama.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.app.db.database import SessionLocal
from backend.app.db.models_sqla import Asset, OnchainMetric, OHLCV

def migrate_historical_onchain():
    db: Session = SessionLocal()
    try:
        assets = db.query(Asset).all()
        for asset in assets:
            print(f"Migrating on-chain padding for {asset.symbol}...")
            
            # Find the date range of OHLCV for this asset
            first_ohlcv = db.query(OHLCV.timestamp).filter(OHLCV.asset_id == asset.id).order_by(OHLCV.timestamp.asc()).first()
            last_ohlcv = db.query(OHLCV.timestamp).filter(OHLCV.asset_id == asset.id).order_by(OHLCV.timestamp.desc()).first()
            
            if not first_ohlcv or not last_ohlcv:
                continue
                
            start_dt = first_ohlcv[0]
            end_dt = last_ohlcv[0]
            
            # Fetch existing onchain metrics
            existing_metrics = db.query(OnchainMetric.timestamp).filter(OnchainMetric.asset_id == asset.id).all()
            existing_dates = {m[0].replace(hour=0, minute=0, second=0, microsecond=0) for m in existing_metrics}
            
            # Generate all dates in range
            curr_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            
            inserts = []
            while curr_dt <= end_dt:
                if curr_dt not in existing_dates:
                    inserts.append(OnchainMetric(
                        asset_id=asset.id,
                        timestamp=curr_dt,
                        tvl=0.0,
                        revenue=0.0,
                        active_users=0.0
                    ))
                curr_dt += timedelta(days=1)
                
            if inserts:
                db.bulk_save_objects(inserts)
                db.commit()
                print(f"Inserted {len(inserts)} zero-padded onchain records for {asset.symbol}.")
                
    finally:
        db.close()

if __name__ == "__main__":
    migrate_historical_onchain()
