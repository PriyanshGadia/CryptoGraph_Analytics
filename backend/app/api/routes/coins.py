from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.deps import get_db
from datetime import datetime, timezone, timedelta
from app.db.models_sqla import Asset
import ccxt.async_support as ccxt

router = APIRouter(prefix="/coins", tags=["coins"])

import asyncio

@router.get("/{symbol}/ohlcv")
async def get_coin_ohlcv(
    symbol: str,
    interval: str = "1h",
    db: Session = Depends(get_db)
):
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    exchange = None
    try:
        exchange = ccxt.binance()
        market_symbol = f"{symbol.upper()}/USDT"
        
        # Native async CCXT network call
        raw_ohlcv = await exchange.fetch_ohlcv(
            market_symbol, 
            timeframe=interval, 
            limit=1500
        )

        
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
        return {
            "data": data,
            "data_freshness_timestamp": datetime.now(timezone.utc).isoformat(),
            "staleness_warning": False,
            "source": "binance_live"
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching OHLCV from Binance for {symbol}: {e}", exc_info=True)
        # Fallback to SQLite if Binance API fails
        from app.db.models_sqla import OHLCV
        from sqlalchemy import desc
        
        db_ohlcv = db.query(OHLCV).filter(
            OHLCV.asset_id == asset.id
        ).order_by(desc(OHLCV.timestamp)).limit(1500).all()
        
        # Reverse to chronological order
        db_ohlcv.reverse()
            
        data = []
        latest_timestamp = None
        for row in db_ohlcv:
            ts_sec = row.timestamp.timestamp() if hasattr(row.timestamp, "timestamp") else datetime.fromisoformat(str(row.timestamp)).timestamp()
            latest_timestamp = ts_sec
            ts_ms = int(ts_sec * 1000)
            data.append({
                "time": ts_ms,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume)
            })
            
        is_stale = False
        if latest_timestamp:
            age_seconds = datetime.now(timezone.utc).timestamp() - latest_timestamp
            is_stale = age_seconds > 300  # Older than 5 minutes
            
        return {
            "data": data,
            "data_freshness_timestamp": datetime.fromtimestamp(latest_timestamp, tz=timezone.utc).isoformat() if latest_timestamp else None,
            "staleness_warning": is_stale,
            "source": "sqlite_fallback"
        }
    finally:
        if exchange:
            try:
                await exchange.close()
            except Exception:
                pass

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
        SELECT 
            strftime('%Y-%m-%dT%H:00:00Z', timestamp) as bucket,
            AVG(rsi_14), AVG(macd), AVG(macd_signal), AVG(atr_14), 
            AVG(bb_width), AVG(returns_1d), AVG(returns_7d), AVG(volatility_7d)
        FROM technical_features
        WHERE asset_id = :asset_id AND timestamp >= :since
        GROUP BY bucket
        ORDER BY bucket ASC
    """), {"asset_id": asset.id, "since": since_str}).fetchall()
        
    data = []
    for row in res:
        # Proper mathematical aggregation per hour
        try:
            ts_dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ts = int(ts_dt.timestamp())
        except Exception:
            continue
            
        data.append({
            "time": ts,
            "rsi_14": row[1] if row[1] is not None else 50.0,
            "macd": row[2] if row[2] is not None else 0.0,
            "macd_signal": row[3] if row[3] is not None else 0.0,
            "atr_14": row[4] if row[4] is not None else 0.0,
            "bb_width": row[5] if row[5] is not None else 0.0,
            "returns_1d": row[6] if row[6] is not None else 0.0,
            "returns_7d": row[7] if row[7] is not None else 0.0,
            "volatility_7d": row[8] if row[8] is not None else 0.0,
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
        
    latest_ohlcv = db.execute(text("SELECT close FROM ohlcv WHERE asset_id = :asset_id ORDER BY timestamp DESC LIMIT 1"), {"asset_id": asset.id}).fetchone()
    latest_price = latest_ohlcv[0] if latest_ohlcv else None

    # Try live websocket state for ultra-recent predictions
    try:
        from app.core.streams.binance_ws import get_global_market_state
        m_state = get_global_market_state()
        if asset.symbol in m_state and m_state[asset.symbol].get("current_price"):
            latest_price = m_state[asset.symbol]["current_price"]
    except Exception:
        pass

    results = []
    correct_count = 0
    total_scored = 0
    conf_sum = 0
    
    for p in preds_res:
        raw_ts = p[0]
        date_str = raw_ts.split("T")[0] if "T" in raw_ts else raw_ts[:10]
        pred_date = datetime.strptime(date_str, "%Y-%m-%d")
        next_day_str = (pred_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        actual_return = None
        was_correct = None
        
        close_today = price_map.get(date_str)
        close_next = price_map.get(next_day_str)

        if close_today and not close_next:
            if latest_price and latest_price > 0:
                close_next = latest_price
        elif not close_today:
            if price_map:
                sorted_dates = sorted(price_map.keys())
                close_today = price_map[sorted_dates[0]]
                close_next = latest_price or price_map[sorted_dates[-1]]

        if close_today and close_next and close_today > 0:
            actual_return = (close_next - close_today) / close_today
            
            direction = p[1] or "neutral"
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
        SELECT asset_id, strftime('%Y-%m-%d', timestamp) as date, AVG(returns_1d) as mean_ret
        FROM technical_features
        WHERE timestamp >= :since
        GROUP BY asset_id, date
    """), {"since": since.isoformat()}).fetchall()
    
    if not res:
        return []
        
    all_data = [{"asset_id": r[0], "date": r[1], "returns_1d": r[2]} for r in res]
    df = pd.DataFrame(all_data)
    
    # We take the mean daily return to aggregate multiple data points into 1 row per day per asset
    pivot = df.pivot_table(index='date', columns='asset_id', values='returns_1d', aggfunc='mean')
    
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
    from app.db.models_sqla import AssetNews
    
    asset = db.query(Asset).filter(Asset.symbol.ilike(symbol)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    
    # Query AssetNews for basic sentiment metrics
    news_res = db.execute(text("""
        SELECT strftime('%Y-%m-%d', published_at) as date, headline
        FROM asset_news
        WHERE asset_id = :asset_id AND published_at >= :since
        ORDER BY published_at ASC
    """), {"asset_id": asset.id, "since": since.isoformat()}).fetchall()
    
    # Group news by date and perform simple lexical sentiment
    sentiment_by_date = {}
    for r in news_res:
        date_str = r[0]
        headline = r[1].lower()
        
        # Extremely basic lexical analysis
        bullish_words = ['surge', 'jump', 'gain', 'high', 'bull', 'buy', 'growth', 'up', 'adopt']
        bearish_words = ['drop', 'fall', 'lose', 'low', 'bear', 'sell', 'crash', 'down', 'hack', 'sec']
        
        score = 0.5 # Neutral
        for w in bullish_words:
            if w in headline: score += 0.2
        for w in bearish_words:
            if w in headline: score -= 0.2
            
        score = max(0.0, min(1.0, score))
        
        if date_str not in sentiment_by_date:
            sentiment_by_date[date_str] = []
        sentiment_by_date[date_str].append(score)
        
    avg_sentiments = {}
    for date_str, scores in sentiment_by_date.items():
        avg_sentiments[date_str] = sum(scores) / len(scores)
    
    # Fill missing dates with Technical Features
    res = db.execute(text("""
        SELECT strftime('%Y-%m-%d', timestamp) as date, returns_1d, rsi_14
        FROM technical_features
        WHERE asset_id = :asset_id AND timestamp >= :since
        ORDER BY timestamp ASC
    """), {"asset_id": asset.id, "since": since.isoformat()}).fetchall()
        
    data = []
    for row in res:
        date_str = row[0]
        ret1d = row[1] or 0.0
        rsi = row[2] or 50.0
        
        # Use NLP sentiment if available, otherwise fallback to RSI-based momentum proxy
        sentiment = avg_sentiments.get(date_str, (rsi / 100.0))
        
        # Fear and Greed approximation (0-100)
        fg = sentiment * 100
        
        data.append({
            "date": date_str,
            "sentiment_score": round(sentiment, 4),
            "fear_greed": round(fg, 2),
            "fear_greed_norm": round(sentiment, 4),
            "community_score": round(sentiment, 4),
            "public_interest": 0
        })
        
    return data

