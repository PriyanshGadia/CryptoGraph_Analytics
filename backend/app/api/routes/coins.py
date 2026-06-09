from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_supabase
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/coins", tags=["coins"])

@router.get("/{symbol}/ohlcv")
async def get_coin_ohlcv(
    symbol: str,
    period: str = "3M",
    db=Depends(get_supabase)
):
    """
    Returns OHLCV candle data for the given period.
    period maps to:
      1W  -> last 7 days
      1M  -> last 30 days
      3M  -> last 90 days
      1Y  -> last 365 days
      ALL -> all available data
    """
    # Look up asset_id
    asset_res = db.table("assets").select("id").ilike("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset_id = asset_res.data[0]["id"]
    
    # Compute since date
    now = datetime.now(timezone.utc)
    if period == "1W":
        since = now - timedelta(days=7)
    elif period == "1M":
        since = now - timedelta(days=30)
    elif period == "3M":
        since = now - timedelta(days=90)
    elif period == "1Y":
        since = now - timedelta(days=365)
    else:
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        
    since_str = since.isoformat()
    
    # Query ohlcv
    ohlcv_res = db.table("ohlcv").select("timestamp, open, high, low, close, volume")\
        .eq("asset_id", asset_id)\
        .gte("timestamp", since_str)\
        .order("timestamp", desc=False)\
        .execute()
        
    data = []
    for row in ohlcv_res.data:
        data.append({
            "date": row["timestamp"].split("T")[0],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"])
        })
        
    return data

@router.get("/{symbol}/indicators")
async def get_coin_indicators(
    symbol: str,
    period: str = "3M",
    db=Depends(get_supabase)
):
    """
    Returns technical indicators for the given period.
    """
    asset_res = db.table("assets").select("id").ilike("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset_id = asset_res.data[0]["id"]
    
    now = datetime.now(timezone.utc)
    if period == "1W":
        since = now - timedelta(days=7)
    elif period == "1M":
        since = now - timedelta(days=30)
    elif period == "3M":
        since = now - timedelta(days=90)
    elif period == "1Y":
        since = now - timedelta(days=365)
    else:
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        
    since_str = since.isoformat()
    
    res = db.table("technical_features")\
        .select("timestamp, rsi_14, macd, macd_signal, atr_14, bb_width, returns_1d, returns_7d, volatility_7d")\
        .eq("asset_id", asset_id)\
        .gte("timestamp", since_str)\
        .order("timestamp", desc=False)\
        .execute()
        
    data = []
    for row in res.data:
        data.append({
            "date": row["timestamp"].split("T")[0],
            "rsi_14": row.get("rsi_14"),
            "macd": row.get("macd"),
            "macd_signal": row.get("macd_signal"),
            "atr_14": row.get("atr_14"),
            "bb_width": row.get("bb_width"),
            "returns_1d": row.get("returns_1d"),
            "returns_7d": row.get("returns_7d"),
            "volatility_7d": row.get("volatility_7d"),
        })
        
    return data

@router.get("/{symbol}/prediction-history")
async def get_coin_prediction_history(symbol: str, db=Depends(get_supabase)):
    """
    Returns last 30 predictions for this coin with accuracy scoring.
    """
    asset_res = db.table("assets").select("id").ilike("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset_id = asset_res.data[0]["id"]
    
    # Get last 30 predictions
    preds_res = db.table("predictions").select("*")\
        .eq("asset_id", asset_id)\
        .order("timestamp", desc=True)\
        .limit(30)\
        .execute()
        
    if not preds_res.data:
        return {"predictions": [], "summary": {"accuracy_pct": 0, "total_scored": 0, "correct_count": 0, "avg_confidence": 0}}
        
    # Get relevant OHLCV to score predictions
    # We need prices for prediction dates and prediction_date + 1
    # Optimization: just get all OHLCV for this asset for the last 40 days to cover it
    oldest_pred_ts = preds_res.data[-1]["timestamp"]
    ohlcv_res = db.table("ohlcv").select("timestamp, close")\
        .eq("asset_id", asset_id)\
        .gte("timestamp", oldest_pred_ts)\
        .execute()
        
    price_map = {}
    for r in ohlcv_res.data:
        date_str = r["timestamp"].split("T")[0]
        price_map[date_str] = r["close"]
        
    results = []
    correct_count = 0
    total_scored = 0
    conf_sum = 0
    
    for p in preds_res.data:
        date_str = p["timestamp"].split("T")[0]
        # Calculate next day string
        pred_date = datetime.strptime(date_str, "%Y-%m-%d")
        next_day_str = (pred_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        actual_return = None
        was_correct = None
        
        if date_str in price_map and next_day_str in price_map:
            close_today = price_map[date_str]
            close_next = price_map[next_day_str]
            actual_return = (close_next - close_today) / close_today
            
            direction = p.get("direction")
            if direction in ["up", "strong_up"] and actual_return > 0:
                was_correct = True
            elif direction in ["down", "strong_down"] and actual_return < 0:
                was_correct = True
            elif direction == "neutral" and abs(actual_return) < 0.01:
                was_correct = True
            else:
                was_correct = False
                
            total_scored += 1
            if was_correct:
                correct_count += 1
                
        conf = p.get("confidence", 0)
        conf_sum += conf
                
        results.append({
            "date": date_str,
            "direction": p.get("direction"),
            "confidence": conf,
            "volatility_regime": p.get("volatility_regime"),
            "actual_return": actual_return,
            "was_correct": was_correct,
            "model_version": p.get("model_version")
        })
        
    accuracy_pct = (correct_count / total_scored * 100) if total_scored > 0 else 0
    avg_confidence = (conf_sum / len(preds_res.data)) if preds_res.data else 0
    
    return {
        "predictions": results,
        "summary": {
            "accuracy_pct": accuracy_pct,
            "total_scored": total_scored,
            "correct_count": correct_count,
            "avg_confidence": avg_confidence
        }
    }

@router.get("/{symbol}/correlations")
async def get_coin_correlations(symbol: str, db=Depends(get_supabase)):
    """
    Returns top 10 most correlated coins to this one.
    """
    import pandas as pd
    
    asset_res = db.table("assets").select("id, symbol, sector, market_cap_usd").execute()
    asset_map = {a["id"]: a for a in asset_res.data}
    symbol_to_id = {a["symbol"].lower(): a["id"] for a in asset_res.data}
    
    if symbol.lower() not in symbol_to_id:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    target_asset_id = symbol_to_id[symbol.lower()]
    
    # Query last 90 days of returns_1d for ALL assets (with pagination)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    
    all_data = []
    start = 0
    limit = 1000
    while True:
        res = db.table("technical_features")\
            .select("asset_id, timestamp, returns_1d")\
            .gte("timestamp", since.isoformat())\
            .range(start, start + limit - 1)\
            .execute()
        all_data.extend(res.data)
        if len(res.data) < limit:
            break
        start += limit
        
    df = pd.DataFrame(all_data)
    if df.empty:
        return []
        
    # Pivot so we have dates as index and assets as columns
    df['date'] = df['timestamp'].apply(lambda x: x.split("T")[0])
    pivot = df.pivot_table(index='date', columns='asset_id', values='returns_1d')
    
    if target_asset_id not in pivot.columns:
        return []
        
    corr = pivot.corr(method='pearson')
    target_corr = corr[target_asset_id].dropna()
    
    # Sort by absolute correlation
    sorted_corr = target_corr.abs().sort_values(ascending=False)
    
    # Get current predictions for all assets
    preds_res = db.table("predictions").select("asset_id, direction")\
        .order("timestamp", desc=True)\
        .limit(200)\
        .execute()
        
    # Keep only the latest prediction per asset
    latest_preds = {}
    for p in preds_res.data:
        aid = p["asset_id"]
        if aid not in latest_preds:
            latest_preds[aid] = p["direction"]
            
    results = []
    for aid, abs_val in sorted_corr.items():
        if aid == target_asset_id:
            continue
        if len(results) >= 10:
            break
            
        real_val = target_corr[aid]
        asset_info = asset_map.get(aid, {})
        
        results.append({
            "symbol": asset_info.get("symbol"),
            "correlation": round(real_val, 4),
            "sector": asset_info.get("sector"),
            "market_cap_usd": asset_info.get("market_cap_usd"),
            "direction": latest_preds.get(aid, "neutral")
        })
        
    return results

@router.get("/{symbol}/sentiment-history")
async def get_coin_sentiment_history(symbol: str, db=Depends(get_supabase)):
    """
    Returns last 90 days of sentiment data for this coin.
    """
    asset_res = db.table("assets").select("id").ilike("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset_id = asset_res.data[0]["id"]
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    
    res = db.table("sentiment").select("timestamp, sentiment_score, fear_greed, fear_greed_norm, community_score, public_interest")\
        .eq("asset_id", asset_id)\
        .gte("timestamp", since.isoformat())\
        .order("timestamp", desc=False)\
        .execute()
        
    data = []
    for row in res.data:
        data.append({
            "date": row["timestamp"].split("T")[0],
            "sentiment_score": row.get("sentiment_score"),
            "fear_greed": row.get("fear_greed"),
            "fear_greed_norm": row.get("fear_greed_norm"),
            "community_score": row.get("community_score"),
            "public_interest": row.get("public_interest")
        })
        
    return data
