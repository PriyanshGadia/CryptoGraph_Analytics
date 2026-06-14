from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.deps import get_db
from datetime import datetime, timezone, timedelta
from app.db.models_sqla import Asset
import ccxt

router = APIRouter(prefix="/coins", tags=["coins"])

@router.get("/{symbol}/ohlcv")
def get_coin_ohlcv(
    symbol: str,
    interval: str = "1h",
    db: Session = Depends(get_db)
):
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    try:
        exchange = ccxt.binance()
        market_symbol = f"{symbol.upper()}/USDT"
        raw_ohlcv = exchange.fetch_ohlcv(market_symbol, timeframe=interval, limit=1500)
        
        data = []
        for row in raw_ohlcv:
            data.append({
                "time": int(row[0] / 1000),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5])
            })
        return data
    except Exception as e:
        print(f"Error fetching OHLCV from Binance: {e}")
        # Fallback to SQLite if Binance API fails
        since = datetime.now(timezone.utc) - timedelta(days=365)
        since_str = since.isoformat()
        
        res = db.execute(text("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE asset_id = :asset_id AND timestamp >= :since
            ORDER BY timestamp ASC
        """), {"asset_id": asset.id, "since": since_str}).fetchall()
            
        data = []
        seen = set()
        for row in res:
            raw_ts = int(datetime.fromisoformat(row[0]).timestamp())
            ts = (raw_ts // 60) * 60
            if ts in seen: continue
            seen.add(ts)
            data.append({
                "time": ts,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5])
            })
            
        return data

@router.get("/{symbol}/indicators")
def get_coin_indicators(
    symbol: str,
    period: str = "3M",
    db: Session = Depends(get_db)
):
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Always fetch 1 Year minimum to allow charting engines to pan backwards indefinitely
    since = datetime.now(timezone.utc) - timedelta(days=365)
    since_str = since.isoformat()
    
    res = db.execute(text("""
        SELECT timestamp, rsi_14, macd, macd_signal, atr_14, bb_width, returns_1d, returns_7d, volatility_7d
        FROM technical_features
        WHERE asset_id = :asset_id AND timestamp >= :since
        ORDER BY timestamp ASC
    """), {"asset_id": asset.id, "since": since_str}).fetchall()
        
    data = []
    seen = set()
    for row in res:
        # Enforce strict 1-minute time bucketing to prevent duplicate/overlapping candles
        raw_ts = int(datetime.fromisoformat(row[0]).timestamp())
        ts = (raw_ts // 60) * 60
        if ts in seen: continue
        seen.add(ts)
        data.append({
            "time": ts,
            "rsi_14": row[1],
            "macd": row[2],
            "macd_signal": row[3],
            "atr_14": row[4],
            "bb_width": row[5],
            "returns_1d": row[6],
            "returns_7d": row[7],
            "volatility_7d": row[8],
        })
        
    return data

@router.get("/{symbol}/prediction-history")
def get_coin_prediction_history(symbol: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    preds_res = db.execute(text("""
        SELECT timestamp, direction, confidence, volatility_regime, model_version
        FROM predictions
        WHERE asset_id = :asset_id
        ORDER BY timestamp DESC
        LIMIT 30
    """), {"asset_id": asset.id}).fetchall()
        
    if not preds_res:
        return {"predictions": [], "summary": {"accuracy_pct": 0, "total_scored": 0, "correct_count": 0, "avg_confidence": 0}}
        
    oldest_pred_ts = preds_res[-1][0]
    ohlcv_res = db.execute(text("""
        SELECT timestamp, close
        FROM ohlcv
        WHERE asset_id = :asset_id AND timestamp >= :since
    """), {"asset_id": asset.id, "since": oldest_pred_ts}).fetchall()
        
    price_map = {}
    for r in ohlcv_res:
        date_str = r[0].split("T")[0]
        price_map[date_str] = r[1]
        
    results = []
    correct_count = 0
    total_scored = 0
    conf_sum = 0
    
    for p in preds_res:
        date_str = p[0].split("T")[0]
        pred_date = datetime.strptime(date_str, "%Y-%m-%d")
        next_day_str = (pred_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        actual_return = None
        was_correct = None
        
        if date_str in price_map and next_day_str in price_map:
            close_today = price_map[date_str]
            close_next = price_map[next_day_str]
            actual_return = (close_next - close_today) / close_today
            
            direction = p[1]
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
                
        conf = p[2] or 0.0
        conf_sum += conf
                
        results.append({
            "date": date_str,
            "direction": p[1],
            "confidence": conf,
            "volatility_regime": p[3],
            "actual_return": actual_return,
            "was_correct": was_correct,
            "model_version": p[4]
        })
        
    accuracy_pct = (correct_count / total_scored * 100) if total_scored > 0 else 0
    avg_confidence = (conf_sum / len(preds_res)) if preds_res else 0
    
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
def get_coin_correlations(symbol: str, db: Session = Depends(get_db)):
    import pandas as pd
    
    assets = db.query(Asset).all()
    asset_map = {a.id: {"symbol": a.symbol, "sector": a.sector, "market_cap_usd": a.market_cap_usd} for a in assets}
    symbol_to_id = {a.symbol.lower(): a.id for a in assets}
    
    if symbol.lower() not in symbol_to_id:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    target_asset_id = symbol_to_id[symbol.lower()]
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    
    res = db.execute(text("""
        SELECT asset_id, timestamp, returns_1d
        FROM technical_features
        WHERE timestamp >= :since
    """), {"since": since.isoformat()}).fetchall()
    
    if not res:
        return []
        
    all_data = [{"asset_id": r[0], "timestamp": r[1], "returns_1d": r[2]} for r in res]
    df = pd.DataFrame(all_data)
    
    df['date'] = df['timestamp'].apply(lambda x: x.split("T")[0])
    pivot = df.pivot_table(index='date', columns='asset_id', values='returns_1d')
    
    if target_asset_id not in pivot.columns:
        return []
        
    corr = pivot.corr(method='pearson')
    target_corr = corr[target_asset_id].dropna()
    
    sorted_corr = target_corr.abs().sort_values(ascending=False)
    
    preds_res = db.execute(text("""
        SELECT asset_id, direction
        FROM predictions
        ORDER BY timestamp DESC
        LIMIT 200
    """)).fetchall()
        
    latest_preds = {}
    for p in preds_res:
        aid = p[0]
        if aid not in latest_preds:
            latest_preds[aid] = p[1]
            
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
def get_coin_sentiment_history(symbol: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    
    res = db.execute(text("""
        SELECT timestamp, sentiment_score, fear_greed, fear_greed_norm, community_score, public_interest
        FROM asset_news
        WHERE asset_id = :asset_id AND timestamp >= :since
        ORDER BY timestamp ASC
    """), {"asset_id": asset.id, "since": since.isoformat()}).fetchall()
        
    data = []
    for row in res:
        data.append({
            "date": row[0].split("T")[0],
            "sentiment_score": row[1],
            "fear_greed": row[2],
            "fear_greed_norm": row[3],
            "community_score": row[4],
            "public_interest": row[5]
        })
        
    return data
