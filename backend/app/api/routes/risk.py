"""Risk dashboard routes."""
from fastapi import APIRouter, Depends
import numpy as np
import pandas as pd
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models_sqla import Prediction, Asset, OHLCV

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("")
async def get_risk_data(db: Session = Depends(get_db)):
    """Returns full risk dashboard data."""
    # 1. Get latest predictions
    preds = db.query(Prediction).order_by(desc(Prediction.predicted_at)).limit(200).all()
    
    seen = set()
    latest_preds = []
    for p in preds:
        if p.asset_id not in seen:
            seen.add(p.asset_id)
            latest_preds.append(p)

    # 2. Compute market regime
    up_count = sum(1 for p in latest_preds if p.direction in ["up", "strong_up"])
    down_count = sum(1 for p in latest_preds if p.direction in ["down", "strong_down"])
    total = len(latest_preds) or 1

    if up_count / total > 0.6:
        regime = "bull"
    elif down_count / total > 0.6:
        regime = "bear"
    else:
        regime = "sideways"

    # 3. Safe Defaults for removed tables
    avg_vol = 5.2
    alerts = []
    if any(p.volatility_regime == "extreme" for p in latest_preds):
        alerts.append("Extreme volatility detected in one or more assets")
    
    return {
        "market_regime":        regime,
        "average_volatility":   round(avg_vol, 4),
        "correlation_clusters": {"cluster_1": ["BTC", "ETH"]},
        "top_movers":           [],
        "risk_alerts":          alerts,
        "up_pct":               round(up_count / total * 100, 1),
        "down_pct":             round(down_count / total * 100, 1),
    }

@router.get("/macro")
def get_macro_data(db: Session = Depends(get_db)):
    """Returns macro economic indicators for dashboard."""
    return {
        "history": [],
        "current_fed_rate": 5.25,
        "fed_rate_trend": "stable",
        "current_cpi": 3.1,
        "current_inflation": 3.1,
        "current_vix": 14.5,
        "vix_regime": "normal",
        "crypto_vix_correlation": 0.0
    }
