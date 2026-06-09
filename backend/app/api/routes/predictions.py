"""Prediction routes."""
import subprocess
from fastapi import APIRouter, Depends, BackgroundTasks
from app.api.deps import get_supabase
from app.db.models import Prediction, PredictionHistory

router = APIRouter(prefix="/predictions", tags=["predictions"])

@router.get("", response_model=list[Prediction])
async def get_predictions(
    limit: int = 50,
    direction: str = "all",           # all | up | down | neutral
    min_confidence: float = 0.0,
    db=Depends(get_supabase)
):
    """Returns latest predictions for all assets with optional filters."""
    query = db.table("predictions").select("*, assets(symbol)").order("timestamp", desc=True).limit(limit)
    
    if direction != "all":
        query = query.eq("direction", direction)
        
    if min_confidence > 0:
        query = query.gte("confidence", min_confidence)
        
    res = query.execute()
    
    predictions = []
    for row in res.data:
        asset_symbol = row.get("assets", {}).get("symbol", "UNKNOWN")
        predictions.append(Prediction(
            asset_symbol=asset_symbol,
            direction=row.get("direction", "neutral"),
            confidence=row.get("confidence", 0.0),
            volatility_regime=row.get("volatility_regime", "medium"),
            predicted_at=str(row.get("timestamp", "")),
            model_version=row.get("model_version", "v1.0")
        ))
    return predictions

@router.get("/{symbol}", response_model=PredictionHistory)
async def get_prediction_history(symbol: str, db=Depends(get_supabase)):
    """Returns last 30 predictions for a single asset."""
    # Find asset
    asset_res = db.table("assets").select("id").eq("symbol", symbol).execute()
    if not asset_res.data:
        return PredictionHistory(symbol=symbol, predictions=[])
        
    asset_id = asset_res.data[0]['id']
    
    res = db.table("predictions").select("*").eq("asset_id", asset_id).order("timestamp", desc=True).limit(30).execute()
    
    preds = []
    for row in res.data:
        preds.append(Prediction(
            asset_symbol=symbol,
            direction=row.get("direction", "neutral"),
            confidence=row.get("confidence", 0.0),
            volatility_regime=row.get("volatility_regime", "medium"),
            predicted_at=str(row.get("timestamp", "")),
            model_version=row.get("model_version", "v1.0")
        ))
        
    return PredictionHistory(symbol=symbol, predictions=preds)

@router.post("/inference/trigger")
async def trigger_inference(background_tasks: BackgroundTasks, db=Depends(get_supabase)):
    """
    Triggers fresh inference run asynchronously.
    Calls ml/pipelines/inference_pipeline.py as subprocess in background.
    Returns immediately: {"status": "triggered", "message": "Inference pipeline started"}
    """
    def run_inference_subprocess():
        subprocess.run(["python", "ml/pipelines/inference_pipeline.py"])
        
    background_tasks.add_task(run_inference_subprocess)
    return {"status": "triggered", "message": "Inference pipeline started in background"}
