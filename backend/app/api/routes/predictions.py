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
from pydantic import BaseModel, Field, field_validator
import re

class BatchPredictionRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1)

    @field_validator("symbols")
    @classmethod
    def validate_symbols_list(cls, v: List[str]) -> List[str]:
        if len(v) > 100:
            raise ValueError("Batch request cannot exceed 100 symbols.")
        for symbol in v:
            if not symbol or len(symbol) < 2 or len(symbol) > 10:
                raise ValueError(f"Symbol '{symbol}' must be between 2 and 10 characters.")
            if not re.match(r"^[a-zA-Z0-9_\-]+$", symbol):
                raise ValueError(f"Symbol '{symbol}' must be alphanumeric URL-safe.")
        return [sym.upper() for sym in v]

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
                confidence=round(pred.confidence * 100.0, 2) if pred.confidence is not None else 0.0,
                confidence_interval=[pred.confidence_interval_lower * 100.0, pred.confidence_interval_upper * 100.0] if pred.confidence_interval_lower is not None and pred.confidence_interval_upper is not None else None,
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
                logging.getLogger(__name__).error(f"Failed to fetch market state for {asset.symbol}: {e}", exc_info=True)
                
        predictions.append(Prediction(
            asset_symbol=asset.symbol,
            direction=pred.direction or "neutral",
            confidence=(pred.confidence * 100.0) if pred.confidence is not None else 0.0,
            volatility_regime=pred.volatility_regime or "medium",
            predicted_at=str(pred.predicted_at or ""),
            model_version=pred.model_version or "v1.0",
            shap_values=sv,
            confidence_interval=[pred.confidence_interval_lower * 100.0, pred.confidence_interval_upper * 100.0] if pred.confidence_interval_lower is not None and pred.confidence_interval_upper is not None else None
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
            confidence=(row.confidence * 100.0) if row.confidence is not None else 0.0,
            volatility_regime=row.volatility_regime or "medium",
            predicted_at=str(row.predicted_at or ""),
            model_version=row.model_version or "v1.0",
            shap_values=sv,
            confidence_interval=[row.confidence_interval_lower * 100.0, row.confidence_interval_upper * 100.0] if row.confidence_interval_lower is not None and row.confidence_interval_upper is not None else None
        ))
        
    return PredictionHistory(symbol=symbol, predictions=preds)

@router.post("/inference/trigger")
@limiter.limit("1/minute")
async def trigger_inference(request: Request, background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)):
    """
    Triggers fresh inference run asynchronously.
    Refreshes technicals, then calls ml/pipelines/inference_pipeline.py.
    """
    from app.tasks import run_inference_pipeline_task
    from app.core.celery_app import celery_app
    
    if celery_app.conf.task_always_eager:
        # Fallback to FastAPI BackgroundTasks to prevent blocking the HTTP response
        background_tasks.add_task(run_inference_pipeline_task)
        return {"status": "triggered", "message": "Inference pipeline started in background task (eager fallback)"}
    else:
        # Trigger true Celery worker task asynchronously
        run_inference_pipeline_task.delay()
        return {"status": "triggered", "message": "Inference pipeline task sent to Celery queue"}

