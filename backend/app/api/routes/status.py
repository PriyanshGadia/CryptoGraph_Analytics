from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from datetime import datetime, timezone

router = APIRouter(prefix="/status", tags=["status"])

@router.get("")
@router.get("/")
async def get_data_status(db=Depends(get_supabase)):
    """Returns when each data source was last updated."""
    
    # Latest OHLCV timestamp
    ohlcv = db.table("ohlcv").select("timestamp").order(
        "timestamp", desc=True).limit(1).execute()
    
    # Latest prediction timestamp
    preds = db.table("predictions").select("predicted_at").order(
        "predicted_at", desc=True).limit(1).execute()
    
    # Latest sentiment timestamp
    sent = db.table("sentiment").select("timestamp").order(
        "timestamp", desc=True).limit(1).execute()
    
    # Latest graph snapshot
    graph = db.table("graph_snapshots").select("timestamp").order(
        "timestamp", desc=True).limit(1).execute()

    def fmt(rows, key):
        if rows and rows[0].get(key):
            return rows[0][key]
        return None

    return {
        "ohlcv_last_updated":       fmt(ohlcv.data, "timestamp"),
        "predictions_last_updated": fmt(preds.data, "predicted_at"),
        "sentiment_last_updated":   fmt(sent.data, "timestamp"),
        "graph_last_updated":       fmt(graph.data, "timestamp"),
        "server_time":              datetime.now(timezone.utc).isoformat(),
        "refresh_intervals": {
            "ohlcv":       "every 5 minutes",
            "sentiment":   "every 1 hour",
            "predictions": "every 24 hours",
            "graph":       "every 24 hours",
        }
    }
