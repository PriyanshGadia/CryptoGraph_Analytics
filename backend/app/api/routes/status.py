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


@router.post("/refresh-all")
async def trigger_refresh_all(db: Session = Depends(get_db)):
    """
    Manually triggers a full data refresh cycle:
    1. Refreshes live technicals (RSI, MACD, returns) from Binance via CCXT
    2. Clears the API response cache
    3. Triggers a prediction broadcast to all connected WebSocket clients
    """
    results = {}

    # 1. Refresh live technicals
    try:
        from app.api.routes.screener import refresh_live_technicals
        tech_result = refresh_live_technicals(db=db)
        results["technicals"] = tech_result.get("message", "done")
    except Exception as e:
        results["technicals"] = f"error: {e}"

    # 2. Clear response cache
    try:
        from app.core.cache import _cache
        cache_count = len(_cache)
        _cache.clear()
        results["cache"] = f"cleared {cache_count} entries"
    except Exception as e:
        results["cache"] = f"error: {e}"

    # 3. Trigger prediction inference pipeline
    try:
        import subprocess
        subprocess.Popen(["python", "ml/pipelines/inference_pipeline.py"])
        results["inference"] = "pipeline triggered"
    except Exception as e:
        results["inference"] = f"error: {e}"
        
    # 4. Trigger prediction broadcast
    try:
        from app.api.routes.stream import FORCE_PREDICTION_BROADCAST
        import app.api.routes.stream as stream_module
        stream_module.FORCE_PREDICTION_BROADCAST = True
        results["predictions_broadcast"] = "broadcast triggered"
    except Exception as e:
        results["predictions_broadcast"] = f"error: {e}"

    return {
        "status": "success",
        "message": "Full refresh cycle completed",
        "details": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

