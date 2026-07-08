"""Prediction routes."""
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.schemas import Prediction, PredictionHistory

from app.api.deps import verify_api_key as get_api_key
from app.api.routes.forecast import limiter

router = APIRouter(prefix="/predictions", tags=["predictions"])

from typing import List
from pydantic import BaseModel

class BatchPredictionRequest(BaseModel):
    symbols: List[str]

@router.post("/batch", response_model=list[Prediction])
async def get_batch_predictions(
    req: BatchPredictionRequest,
    db: Session = Depends(get_db)
):
    """Perform bulk inference lookup/computation for a batch of assets."""
    from app.db.models import Prediction as SQLAPrediction, Asset
    from sqlalchemy import desc
    import json
    
    results = []
    for symbol in req.symbols:
        asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
        if not asset:
            continue
        
        pred = db.query(SQLAPrediction).filter(SQLAPrediction.asset_id == asset.id).order_by(desc(SQLAPrediction.predicted_at)).first()
        if pred:
            sv = None
            if pred.shap_values:
                try:
                    sv_str = pred.shap_values if isinstance(pred.shap_values, str) else json.dumps(pred.shap_values)
                    if len(sv_str) < 5000:
                        sv = json.loads(sv_str) if isinstance(pred.shap_values, str) else pred.shap_values
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to fetch SHAP for {symbol}: {e}", exc_info=True)
                    
            results.append(Prediction(
                asset_symbol=asset.symbol,
                direction=pred.direction,
                confidence=round(pred.confidence, 2) if pred.confidence else 0.0,
                confidence_interval=[pred.confidence_interval_lower, pred.confidence_interval_upper] if pred.confidence_interval_lower else None,
                volatility_regime=pred.volatility_regime or "medium",
                predicted_at=pred.predicted_at.isoformat() if hasattr(pred.predicted_at, 'isoformat') else str(pred.predicted_at),
                shap_values=sv,
                model_version=pred.model_version or "stgcn-v1.0"
            ))
    return results

@router.get("/validation-metrics")
async def get_validation_metrics():
    """Returns the latest audited model validation metrics from validation_metrics.json."""
    import json
    from pathlib import Path
    
    paths = [
        Path(__file__).resolve().parent.parent.parent.parent / "ml" / "artifacts" / "validation_metrics.json",
        Path("ml/artifacts/validation_metrics.json"),
        Path("../ml/artifacts/validation_metrics.json")
    ]
    
    for p in paths:
        if p.exists() and p.is_file():
            try:
                with open(p, "r") as f:
                    data = json.load(f)
                    data["status"] = "audited"
                    return data
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to read metrics from {p}: {e}", exc_info=True)
    return {
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "max_drawdown": None,
        "profit_factor": None,
        "win_rate": None,
        "f1_macro": None,
        "precision_macro": None,
        "recall_macro": None,
        "status": "awaiting_calibration",
        "message": "Model calibration in progress. Audited backtesting metrics not yet available."
    }

@router.get("", response_model=list[Prediction])
async def get_predictions(
    limit: int = 50,
    days: int = 7,
    direction: str = "all",           # all | up | down | neutral
    min_confidence: float = 0.0,
    db: Session = Depends(get_db)
):
    """Returns latest predictions for all assets with optional filters."""
    from datetime import datetime, timedelta, timezone
    from app.db.models import Prediction as SQLAPrediction, Asset
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(SQLAPrediction, Asset).join(Asset).filter(SQLAPrediction.predicted_at >= cutoff)
    
    def apply_filters(q):
        if direction != "all":
            q = q.filter(SQLAPrediction.direction == direction)
        if min_confidence > 0:
            q = q.filter(SQLAPrediction.confidence >= min_confidence)
        return q

    query = apply_filters(query)
    res = query.order_by(desc(SQLAPrediction.predicted_at)).limit(min(1000, limit * 20)).all()
    
    if not res:
        query_fallback = apply_filters(db.query(SQLAPrediction, Asset).join(Asset))
        res = query_fallback.order_by(desc(SQLAPrediction.predicted_at)).limit(200).all()
    
    predictions = []
    seen_assets = set()
    for pred, asset in res:
        if asset.symbol in seen_assets:
            continue
        seen_assets.add(asset.symbol)
        
        import json
        sv = None
        if pred.shap_values:
            try:
                sv_str = pred.shap_values if isinstance(pred.shap_values, str) else json.dumps(pred.shap_values)
                if len(sv_str) < 5000:
                    sv = json.loads(sv_str) if isinstance(pred.shap_values, str) else pred.shap_values
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to fetch market state for {s}: {e}", exc_info=True)
                
        predictions.append(Prediction(
            asset_symbol=asset.symbol,
            direction=pred.direction or "neutral",
            confidence=pred.confidence or 0.0,
            volatility_regime=pred.volatility_regime or "medium",
            predicted_at=str(pred.predicted_at or ""),
            model_version=pred.model_version or "v1.0",
            shap_values=sv,
            confidence_interval=[pred.confidence_interval_lower, pred.confidence_interval_upper] if pred.confidence_interval_lower is not None and pred.confidence_interval_upper is not None else None
        ))
        
        if len(predictions) >= limit:
            break
            
    return predictions

@router.get("/{symbol}", response_model=PredictionHistory)
async def get_prediction_history(symbol: str, db: Session = Depends(get_db)):
    """Returns last 30 predictions for a single asset."""
    from app.db.models import Prediction as SQLAPrediction, Asset
    
    # Find asset
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        return PredictionHistory(symbol=symbol, predictions=[])
        
    res = db.query(SQLAPrediction).filter(SQLAPrediction.asset_id == asset.id).order_by(desc(SQLAPrediction.predicted_at)).limit(30).all()
    
    preds = []
    for row in res:
        import json
        sv = None
        if row.shap_values:
            try:
                sv_str = row.shap_values if isinstance(row.shap_values, str) else json.dumps(row.shap_values)
                if len(sv_str) < 5000:
                    sv = json.loads(sv_str) if isinstance(row.shap_values, str) else row.shap_values
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to fetch historical market state: {e}", exc_info=True)
                
        preds.append(Prediction(
            asset_symbol=symbol,
            direction=row.direction or "neutral",
            confidence=row.confidence or 0.0,
            volatility_regime=row.volatility_regime or "medium",
            predicted_at=str(row.predicted_at or ""),
            model_version=row.model_version or "v1.0",
            shap_values=sv,
            confidence_interval=[row.confidence_interval_lower, row.confidence_interval_upper] if row.confidence_interval_lower is not None and row.confidence_interval_upper is not None else None
        ))
        
    return PredictionHistory(symbol=symbol, predictions=preds)

@router.post("/inference/trigger")
@limiter.limit("1/minute")
async def trigger_inference(request: Request, background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)):
    """
    Triggers fresh inference run asynchronously.
    Refreshes technicals, then calls ml/pipelines/inference_pipeline.py as subprocess in background.
    Returns immediately: {"status": "triggered", "message": "Inference pipeline started"}
    """
    async def run_inference_subprocess():
        import asyncio
        from datetime import datetime, timezone
        from app.db.database import SessionLocal
        from app.db.models import AppSetting
        from app.api.routes.screener import refresh_live_technicals
        
        db = SessionLocal()
        lock_key = "inference_trigger_lock"
        try:
            # Simple lock
            lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).with_for_update().first()
            now_ts = datetime.now(timezone.utc).timestamp()
            if lock_setting:
                try:
                    if now_ts - float(lock_setting.setting_value) < 300:
                        print("[Scheduler] Inference already running. Skipping.")
                        return
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to calculate direction for {symbol}: {e}", exc_info=True)
                lock_setting.setting_value = str(now_ts)
            else:
                lock_setting = AppSetting(setting_key=lock_key, setting_value=str(now_ts))
                db.add(lock_setting)
            db.commit()
            
            print("[Scheduler] Refreshing live technicals...")
            await asyncio.wait_for(asyncio.to_thread(refresh_live_technicals, db=db), timeout=60.0)
            
            print("[Scheduler] Running inference pipeline...")
            from ml.pipelines.inference_pipeline import main as run_inference_main
            await asyncio.wait_for(asyncio.to_thread(run_inference_main), timeout=300.0)
            
            print("[Scheduler] Inference completed.")
            
            # Refresh SSOT so /api/assets immediately reflects new confidence scores
            from app.core.streams.binance_ws import refresh_predictions_in_ssot
            await asyncio.to_thread(refresh_predictions_in_ssot, db)
            print("[Scheduler] SSOT prediction cache refreshed.")
            
        except asyncio.TimeoutError:
            print("[Scheduler] Inference pipeline timed out.")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[Scheduler] Error: {e}", exc_info=True)
        finally:
            try:
                lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).first()
                if lock_setting:
                    lock_setting.setting_value = "0"
                    db.commit()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to release lock: {e}", exc_info=True)
            finally:
                db.close()
            
    background_tasks.add_task(run_inference_subprocess)
    return {"status": "triggered", "message": "Full pipeline triggered in background"}
