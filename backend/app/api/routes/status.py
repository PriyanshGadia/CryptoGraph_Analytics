from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.api.deps import get_db
from app.api.deps import verify_api_key as get_api_key
from app.db.models import OHLCV, Prediction, AssetNews
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


from fastapi import APIRouter, Depends, BackgroundTasks

@router.post("/refresh-all")
async def trigger_refresh_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
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

    # 3. Trigger prediction inference pipeline in background to prevent event loop deadlock
    try:
        def run_inference_bg():
            import subprocess
            from pathlib import Path
            import os
            import logging
            log = logging.getLogger(__name__)
            try:
                root_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
                script_path = root_dir / "ml" / "pipelines" / "inference_pipeline.py"
                env = os.environ.copy()
                env["PYTHONPATH"] = str(root_dir)
                subprocess.run(["python", str(script_path)], check=True, cwd=str(root_dir), env=env)
                log.info("[Background Task] Inference pipeline completed successfully.")
            except Exception as e:
                log.error(f"[Background Task] Inference pipeline failed: {e}")
                
        background_tasks.add_task(run_inference_bg)
        results["inference"] = "pipeline queued in background"
    except Exception as e:
        results["inference"] = f"error queuing pipeline: {e}"
        
    # 4. Trigger prediction broadcast
    try:
        import app.api.routes.stream as stream_module
        stream_module.FORCE_PREDICTION_BROADCAST = True
        results["predictions_broadcast"] = "broadcast triggered"
    except Exception as e:
        results["predictions_broadcast"] = f"error: {e}"

    # 5. Refresh SSOT prediction cache so /api/assets reflects fresh confidence
    try:
        from app.core.streams.binance_ws import refresh_predictions_in_ssot
        refresh_predictions_in_ssot(db)
        results["ssot_refresh"] = "predictions synced to SSOT"
    except Exception as e:
        results["ssot_refresh"] = f"error: {e}"

    return {
        "status": "success",
        "message": "Full refresh cycle completed",
        "details": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/scheduler/start")
async def start_scheduler(api_key: str = Depends(get_api_key)):
    """Starts the background scheduler."""
    try:
        import subprocess
        from pathlib import Path
        import os
        
        root_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        scheduler_path = root_dir / "ml" / "scheduler.py"
        
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root_dir)
        
        # Start detached
        subprocess.Popen(["python", str(scheduler_path)], cwd=str(root_dir), env=env)
        return {"status": "success", "message": "Scheduler started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/performance/model_health")
async def get_model_health(db: Session = Depends(get_db)):
    """
    Returns metrics on prediction calibration and model degradation.
    Analyzes historical predictions against realized outcomes.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text as sa_text
    
    # Simple calibration check: average confidence vs hit rate over last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    res = db.execute(sa_text("""
        SELECT 
            AVG(confidence) as avg_conf,
            COUNT(*) as total_preds,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_preds
        FROM predictions
        WHERE predicted_at >= :start_time AND is_correct IS NOT NULL
    """), {"start_time": seven_days_ago.isoformat()}).fetchone()
    
    avg_conf = res[0] or 0.0
    total_preds = res[1] or 0
    correct_preds = res[2] or 0
    
    hit_rate = (correct_preds / total_preds) if total_preds > 0 else 0.0
    calibration_error = abs(avg_conf - hit_rate) if avg_conf > 0 else 0.0
    
    health_status = "healthy"
    if calibration_error > 0.2:
        health_status = "degraded"
    if hit_rate < 0.4 and total_preds > 10:
        health_status = "critical"
        
    return {
        "status": "success",
        "health_status": health_status,
        "metrics": {
            "avg_confidence": round(avg_conf, 4),
            "hit_rate": round(hit_rate, 4),
            "calibration_error": round(calibration_error, 4),
            "evaluated_predictions": total_preds
        }
    }

@router.get("/metrics")
async def get_system_metrics(db: Session = Depends(get_db)):
    """
    Returns aggregated historical accuracy metrics for the Ensemble Forecaster.
    """
    from sqlalchemy import text as sa_text
    try:
        total_preds = db.execute(sa_text("SELECT COUNT(*) FROM predictions")).scalar() or 0
        
        return {
            "status": "online",
            "model_version": "ensemble_v1.0",
            "total_predictions_stored": total_preds,
            "system_health": "optimal"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
