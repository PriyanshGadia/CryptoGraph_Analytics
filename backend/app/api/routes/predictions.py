"""Prediction routes."""
import subprocess
from fastapi import APIRouter, Depends, BackgroundTasks
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models import Prediction, PredictionHistory

from app.core.auth import get_api_key

router = APIRouter(prefix="/predictions", tags=["predictions"])

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
            except Exception:
                pass
                
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
    from app.db.models_sqla import Prediction as SQLAPrediction, Asset
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(SQLAPrediction, Asset).join(Asset).filter(SQLAPrediction.predicted_at >= cutoff)
    
    if direction != "all":
        query = query.filter(SQLAPrediction.direction == direction)
        
    if min_confidence > 0:
        query = query.filter(SQLAPrediction.confidence >= min_confidence)
        
    res = query.order_by(desc(SQLAPrediction.predicted_at)).limit(min(1000, limit * 20)).all()
    if not res:
        query_fallback = db.query(SQLAPrediction, Asset).join(Asset)
        if direction != "all":
            query_fallback = query_fallback.filter(SQLAPrediction.direction == direction)
        if min_confidence > 0:
            query_fallback = query_fallback.filter(SQLAPrediction.confidence >= min_confidence)
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
                sv = pred.shap_values if isinstance(pred.shap_values, dict) else json.loads(pred.shap_values)
            except Exception:
                pass
                
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
    from app.db.models_sqla import Prediction as SQLAPrediction, Asset
    
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
                sv = row.shap_values if isinstance(row.shap_values, dict) else json.loads(row.shap_values)
            except Exception:
                pass
                
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
async def trigger_inference(background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)):
    """
    Triggers fresh inference run asynchronously.
    Refreshes technicals, then calls ml/pipelines/inference_pipeline.py as subprocess in background.
    Returns immediately: {"status": "triggered", "message": "Inference pipeline started"}
    """
    def run_inference_subprocess():
        from app.db.database import SessionLocal
        from app.api.routes.screener import refresh_live_technicals
        
        db = SessionLocal()
        try:
            print("[Scheduler] Refreshing live technicals...")
            refresh_live_technicals(db=db)
            print("[Scheduler] Running inference pipeline...")
            from ml.pipelines.inference_pipeline import main as run_inference_main
            run_inference_main()
            print("[Scheduler] Inference completed.")
            
            # Refresh SSOT so /api/assets immediately reflects new confidence scores
            from app.core.streams.binance_ws import refresh_predictions_in_ssot
            refresh_predictions_in_ssot(db)
            print("[Scheduler] SSOT prediction cache refreshed.")
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
        finally:
            db.close()
            
    background_tasks.add_task(run_inference_subprocess)
    return {"status": "triggered", "message": "Full pipeline triggered in background"}
