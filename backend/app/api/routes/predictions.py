"""Prediction routes."""
import subprocess
from fastapi import APIRouter, Depends, BackgroundTasks
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models import Prediction, PredictionHistory

router = APIRouter(prefix="/predictions", tags=["predictions"])

@router.get("", response_model=list[Prediction])
async def get_predictions(
    limit: int = 50,
    direction: str = "all",           # all | up | down | neutral
    min_confidence: float = 0.0,
    db: Session = Depends(get_db)
):
    """Returns latest predictions for all assets with optional filters."""
    from app.db.models_sqla import Prediction as SQLAPrediction, Asset
    
    query = db.query(SQLAPrediction, Asset).join(Asset)
    
    if direction != "all":
        query = query.filter(SQLAPrediction.direction == direction)
        
    if min_confidence > 0:
        query = query.filter(SQLAPrediction.confidence >= min_confidence)
        
    res = query.order_by(desc(SQLAPrediction.predicted_at)).limit(limit).all()
    
    predictions = []
    for pred, asset in res:
        import json
        sv = None
        if pred.shap_values:
            try:
                sv = pred.shap_values if isinstance(pred.shap_values, dict) else json.loads(pred.shap_values)
            except:
                pass
                
        predictions.append(Prediction(
            asset_symbol=asset.symbol,
            direction=pred.direction or "neutral",
            confidence=pred.confidence or 0.0,
            volatility_regime=pred.volatility_regime or "medium",
            predicted_at=str(pred.predicted_at or ""),
            model_version=pred.model_version or "v1.0",
            shap_values=sv
        ))
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
            except:
                pass
                
        preds.append(Prediction(
            asset_symbol=symbol,
            direction=row.direction or "neutral",
            confidence=row.confidence or 0.0,
            volatility_regime=row.volatility_regime or "medium",
            predicted_at=str(row.predicted_at or ""),
            model_version=row.model_version or "v1.0",
            shap_values=sv
        ))
        
    return PredictionHistory(symbol=symbol, predictions=preds)

@router.post("/inference/trigger")
async def trigger_inference(background_tasks: BackgroundTasks):
    """
    Triggers fresh inference run asynchronously.
    Calls ml/pipelines/inference_pipeline.py as subprocess in background.
    Returns immediately: {"status": "triggered", "message": "Inference pipeline started"}
    """
    def run_inference_subprocess():
        subprocess.run(["python", "ml/pipelines/inference_pipeline.py"])
        
    background_tasks.add_task(run_inference_subprocess)
    return {"status": "triggered", "message": "Inference pipeline started in background"}
