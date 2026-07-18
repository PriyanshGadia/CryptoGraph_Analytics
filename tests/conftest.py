import os
import pytest
from datetime import datetime, timezone, timedelta
import uuid

# Force testing environment configuration before any other code imports
os.environ["TESTING"] = "True"

@pytest.fixture(scope="session", autouse=True)
def seed_test_database():
    """
    Synchronously seed the database with mock assets, OHLCV, technical features, and predictions
    so that tests do not experience race conditions with the background seeder.
    """
    from app.db.database import SessionLocal, engine, Base
    import app.db.models as models
    
    # Recreate tables to ensure clean state
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Seed BTC and DYDX assets
        btc_id = str(uuid.uuid4())
        dydx_id = str(uuid.uuid4())
        
        btc = models.Asset(id=btc_id, symbol="BTC", name="Bitcoin", sector="Layer 1")
        dydx = models.Asset(id=dydx_id, symbol="DYDX", name="dYdX", sector="DeFi")
        
        db.add(btc)
        db.add(dydx)
        db.commit()
        
        # Seed OHLCV data for both assets (70 days of data ending today)
        now = datetime.now(timezone.utc)
        for i in range(70):
            timestamp = now - timedelta(days=70 - i)
            # BTC
            btc_ohlcv = models.OHLCV(
                asset_id=btc_id,
                timestamp=timestamp,
                open=60000.0 + i * 10,
                high=61000.0 + i * 10,
                low=59000.0 + i * 10,
                close=60500.0 + i * 10,
                volume=1000.0
            )
            # DYDX
            dydx_ohlcv = models.OHLCV(
                asset_id=dydx_id,
                timestamp=timestamp,
                open=2.0 + i * 0.01,
                high=2.1 + i * 0.01,
                low=1.9 + i * 0.01,
                close=2.05 + i * 0.01,
                volume=50000.0
            )
            # Technical features (required by forecast and backtest pipelines)
            btc_tf = models.TechnicalFeature(
                asset_id=btc_id,
                timestamp=timestamp,
                rsi_14=55.0,
                returns_1d=0.001,
                returns_7d=0.01,
                volatility_7d=0.02,
                macd=0.0,
                macd_signal=0.0,
                atr_14=100.0,
                bb_width=0.05
            )
            dydx_tf = models.TechnicalFeature(
                asset_id=dydx_id,
                timestamp=timestamp,
                rsi_14=52.0,
                returns_1d=0.002,
                returns_7d=0.015,
                volatility_7d=0.03,
                macd=0.0,
                macd_signal=0.0,
                atr_14=0.05,
                bb_width=0.04
            )
            btc_pred = models.Prediction(
                asset_id=btc_id,
                timestamp=timestamp,
                predicted_at=timestamp,
                direction="up",
                confidence=0.75,
                confidence_interval_lower=0.70,
                confidence_interval_upper=0.80,
                volatility_regime="medium",
                model_version="stgcn-v1.0",
                baseline_probability=0.3333
            )
            dydx_pred = models.Prediction(
                asset_id=dydx_id,
                timestamp=timestamp,
                predicted_at=timestamp,
                direction="up",
                confidence=0.80,
                confidence_interval_lower=0.75,
                confidence_interval_upper=0.85,
                volatility_regime="low",
                model_version="stgcn-v1.0",
                baseline_probability=0.3333
            )
            db.add(btc_ohlcv)
            db.add(dydx_ohlcv)
            db.add(btc_tf)
            db.add(dydx_tf)
            db.add(btc_pred)
            db.add(dydx_pred)
            
        db.commit()
        
    finally:
        db.close()
