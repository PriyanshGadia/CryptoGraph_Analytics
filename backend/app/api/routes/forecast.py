"""
On-demand deep learning forecast endpoint.
Fetches 60 days of OHLCV, runs LSTM+Prophet ensemble, returns forecast.
"""
import sys
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from app.api.deps import get_supabase

router = APIRouter(prefix="/forecast", tags=["forecast"])

@router.get("/{symbol}")
async def get_forecast(symbol: str, db=Depends(get_supabase)):
    """
    Runs deep learning forecast for a symbol using last 60 days of data.
    Returns historical prices + 7-day forecast + confidence intervals +
    comparison with ST-GCN model prediction.
    Takes 10-20 seconds to run — frontend should show loading state.
    """
    
    # 1. Get asset_id
    asset_res = db.table("assets").select("id,symbol,name").eq(
        "symbol", symbol.upper()).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    asset = asset_res.data[0]
    asset_id = asset["id"]
    
    # 2. Fetch last 60 days of OHLCV
    since = (datetime.now(timezone.utc) - timedelta(days=65)).isoformat()
    ohlcv_res = (db.table("ohlcv")
        .select("timestamp,open,high,low,close,volume")
        .eq("asset_id", asset_id)
        .gte("timestamp", since)
        .order("timestamp", desc=False)
        .execute())
    
    if not ohlcv_res.data or len(ohlcv_res.data) < 10:
        # Return a helpful message instead of crashing
        return {
            "symbol": symbol.upper(),
            "error": f"Not enough data for {symbol} — only "
                     f"{len(ohlcv_res.data or [])} days available. "
                     f"Need at least 10 days.",
            "historical": [],
            "forecast_prices": [],
            "forecast_dates": [],
            "lower_bound": [],
            "upper_bound": [],
            "model_used": "unavailable",
            "dl_direction": "neutral",
            "dl_change_pct": 0.0,
            "stgcn_direction": "neutral",
            "stgcn_confidence": 0.0,
            "stgcn_volatility": "unknown",
            "models_agree": False,
            "agreement_signal": "INSUFFICIENT DATA",
            "ensemble": False,
        }
    
    df = pd.DataFrame(ohlcv_res.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["close"]     = pd.to_numeric(df["close"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp")
    
    prices = df["close"]
    dates  = df["timestamp"]
    
    # 3. Run ensemble forecast (add ml/ to path)
    import importlib.util, os
    ml_path = os.path.join(os.path.dirname(__file__), 
                           "../../../../ml/models/forecast_model.py")
    spec = importlib.util.spec_from_file_location("forecast_model", ml_path)
    fm   = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fm)
    
    forecast = fm.run_ensemble_forecast(prices, dates, forecast_days=7)
    
    # 4. Get ST-GCN model prediction for this asset
    pred_res = (db.table("predictions")
        .select("direction,confidence,volatility_regime,predicted_at")
        .eq("asset_id", asset_id)
        .order("predicted_at", desc=True)
        .limit(1)
        .execute())
    
    stgcn_pred = pred_res.data[0] if pred_res.data else {
        "direction": "neutral", "confidence": 0.5,
        "volatility_regime": "medium", "predicted_at": None
    }
    
    # 5. Compute comparison metrics
    last_price = float(prices.iloc[-1])
    forecast_end = forecast["forecast_prices"][-1]
    lstm_direction = (
        "up"       if forecast_end > last_price * 1.01 else
        "down"     if forecast_end < last_price * 0.99 else
        "neutral"
    )
    
    lstm_change_pct = round((forecast_end - last_price) / last_price * 100, 2)
    
    # Agreement between ST-GCN and LSTM
    stgcn_dir = stgcn_pred["direction"]
    stgcn_bullish = stgcn_dir in ["up", "strong_up"]
    lstm_bullish  = lstm_direction == "up"
    models_agree  = stgcn_bullish == lstm_bullish
    
    # 6. Generate forecast dates
    last_date = dates.iloc[-1]
    forecast_dates = [
        (last_date + timedelta(days=i+1)).strftime("%Y-%m-%d")
        for i in range(7)
    ]
    
    # 7. Build historical data for chart (last 60 days)
    historical = [
        {
            "date":   row["timestamp"].strftime("%Y-%m-%d"),
            "open":   float(row["open"]) if row["open"] else None,
            "high":   float(row["high"]) if row["high"] else None,
            "low":    float(row["low"])  if row["low"]  else None,
            "close":  float(row["close"]),
            "volume": float(row["volume"]) if row["volume"] else None,
        }
        for _, row in df.iterrows()
    ]
    
    return {
        "symbol":         symbol.upper(),
        "last_price":     round(last_price, 8),
        "last_date":      last_date.strftime("%Y-%m-%d"),
        
        # Historical data for chart
        "historical":     historical,
        
        # Deep learning forecast
        "forecast_dates":  forecast_dates,
        "forecast_prices": forecast["forecast_prices"],
        "lower_bound":     forecast["lower_bound"],
        "upper_bound":     forecast["upper_bound"],
        "model_used":      forecast["model_used"],
        "lstm_forecast":   forecast.get("lstm_forecast"),
        "prophet_forecast":forecast.get("prophet_forecast"),
        "ensemble":        forecast.get("ensemble", False),
        
        # DL model direction assessment
        "dl_direction":    lstm_direction,
        "dl_change_pct":   lstm_change_pct,
        
        # ST-GCN model prediction
        "stgcn_direction":   stgcn_pred["direction"],
        "stgcn_confidence":  round(stgcn_pred["confidence"] * 100, 1),
        "stgcn_volatility":  stgcn_pred["volatility_regime"],
        "stgcn_predicted_at":stgcn_pred["predicted_at"],
        
        # Agreement analysis
        "models_agree":    models_agree,
        "agreement_signal": (
            "STRONG BUY — Both models bullish"     if models_agree and lstm_bullish  else
            "STRONG SELL — Both models bearish"    if models_agree and not lstm_bullish else
            "CONFLICTING — Models disagree"
        )
    }
