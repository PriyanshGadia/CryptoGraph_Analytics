from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.api.deps import get_db
from app.db.models_sqla import OHLCV, Prediction, AssetNews
from datetime import datetime, timezone

router = APIRouter(prefix="/status", tags=["status"])

@router.get("")
@router.get("/")
async def get_data_status(db: Session = Depends(get_db)):
    """Returns when each data source was last updated."""
    
    # Latest OHLCV timestamp
    ohlcv = db.query(OHLCV.timestamp).order_by(desc(OHLCV.timestamp)).first()
    
    # Latest prediction timestamp
    preds = db.query(Prediction.predicted_at).order_by(desc(Prediction.predicted_at)).first()
    
    # Latest sentiment timestamp (AssetNews as proxy)
    sent = db.query(AssetNews.created_at).order_by(desc(AssetNews.created_at)).first()

    def fmt(val):
        if val and val[0]:
            return val[0].isoformat() if isinstance(val[0], datetime) else str(val[0])
        return None

    return {
        "ohlcv_last_updated":       fmt(ohlcv),
        "predictions_last_updated": fmt(preds),
        "sentiment_last_updated":   fmt(sent),
        "graph_last_updated":       fmt(preds), # Graph is built during prediction
        "server_time":              datetime.now(timezone.utc).isoformat(),
        "refresh_intervals": {
            "ohlcv":       "every 5 minutes",
            "sentiment":   "every 1 hour",
            "predictions": "every 24 hours",
            "graph":       "every 24 hours",
        }
    }
