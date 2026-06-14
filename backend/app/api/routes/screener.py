from fastapi import APIRouter, Depends
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from typing import List, Optional
from datetime import datetime
import pandas as pd
import yfinance as yf
import numpy as np
import ccxt
import concurrent.futures
from app.db.models_sqla import Prediction, Asset, OHLCV
from app.core.cache import cached
from app.core.streams.binance_ws import LIVE_OHLCV_CACHE

def get_volatility_regime(vol: float) -> str:
    if vol < 0.025: return "low"
    if vol <= 0.040: return "medium"
    if vol <= 0.065: return "high"
    return "extreme"

router = APIRouter(prefix="/screener", tags=["screener"])

@router.get("/")
@cached(ttl_seconds=300)
def screen_assets(
    direction: str = "all",        # all,strong_up,up,neutral,down,strong_down
    min_confidence: float = 0.0,   # 0.0 to 100.0
    max_confidence: float = 100.0,
    volatility: str = "all",       # all,low,medium,high,extreme
    sector: str = "all",           # all,layer1,defi,exchange,payment,gaming,privacy,storage,other
    min_rsi: float = 0.0,
    max_rsi: float = 100.0,
    min_market_cap: float = 0.0,
    sort_by: str = "confidence",   # confidence,market_cap,returns_1d,volatility_7d,rsi_14
    sort_dir: str = "desc",        # asc,desc
    db: Session = Depends(get_db)
):
    """
    Returns filtered and sorted list of assets.
    """
    # 1. Get all assets
    assets = db.query(Asset).all()
    
    # Get latest predictions
    preds = db.query(Prediction).order_by(desc(Prediction.predicted_at)).limit(200).all()
    latest_preds = {}
    for p in preds:
        if p.asset_id not in latest_preds:
            latest_preds[p.asset_id] = p
            
    # Get latest technical features for all assets in one batched query (No N+1)
    tech_query = """
        SELECT asset_id, rsi_14, macd, returns_1d, returns_7d, volatility_7d 
        FROM technical_features 
        WHERE (asset_id, timestamp) IN (
            SELECT asset_id, MAX(timestamp) 
            FROM technical_features 
            GROUP BY asset_id
        )
    """
    tech_results = db.execute(text(tech_query)).fetchall()
    latest_tech = {t[0]: {"rsi_14": t[1], "macd": t[2], "returns_1d": t[3], "returns_7d": t[4], "volatility_7d": t[5]} for t in tech_results}
            
    # Apply filters
    results = []
    for a in assets:
        # Fetch real technicals from batched query
        t_data = latest_tech.get(a.id, {})
        t_rsi = t_data.get("rsi_14", 50.0)
        t_macd = t_data.get("macd", 0.0)
        t_ret1d = t_data.get("returns_1d", 0.0)
        t_ret7d = t_data.get("returns_7d", 0.0)
        t_vol7d = t_data.get("volatility_7d", 0.0)
        
        pred = latest_preds.get(a.id)
        # Use defaults if prediction is missing
        if pred:
            p_dir = pred.direction or "neutral"
            p_conf = pred.confidence or 0.0
            p_vol = get_volatility_regime(t_vol7d)
            pred_time = pred.predicted_at.isoformat() if pred.predicted_at else None
        else:
            p_dir = "neutral"
            p_conf = 0.0
            p_vol = get_volatility_regime(t_vol7d)
            pred_time = None
            
        a_sec = a.sector or "other"
        
        a_mcap = a.market_cap_usd or 0.0
        
        # Check filters
        if direction != "all" and p_dir != direction: continue
        if p_conf < min_confidence or p_conf > max_confidence: continue
        if volatility != "all" and p_vol != volatility: continue
        if sector != "all" and a_sec != sector: continue
        if t_rsi < min_rsi or t_rsi > max_rsi: continue
        if a_mcap < min_market_cap: continue
        
        # Check live cache for current price
        live_cache = LIVE_OHLCV_CACHE.get(a.symbol)
        c_price = live_cache[-1]["close"] if live_cache else 0.0
        
        # Build record
        record = {
            "symbol": a.symbol,
            "name": a.name,
            "sector": a_sec,
            "market_cap_usd": a_mcap,
            "current_price": c_price,
            "price_change_24h_pct": t_ret1d,
            "direction": p_dir,
            "confidence": p_conf,
            "volatility_regime": p_vol,
            "rsi_14": t_rsi,
            "macd": t_macd,
            "returns_1d": t_ret1d,
            "returns_7d": t_ret7d,
            "volatility_7d": t_vol7d,
            "predicted_at": pred_time
        }
        results.append(record)
        
    # Sort
    # handle None values in sort keys safely
    reverse = (sort_dir == "desc")
    def safe_sort_key(item):
        val = item.get(sort_by)
        if sort_by in ["symbol", "sector"]:
            if val is None:
                return "" if not reverse else "zzzzzz"
            return str(val).lower()
        else:
            if val is None:
                return -float('inf') if reverse else float('inf')
            return float(val)
        
    results.sort(key=safe_sort_key, reverse=reverse)
    
    return results

@router.get("/presets/{preset_name}")
def get_preset_scan(preset_name: str, db: Session = Depends(get_db)):
    """
    Returns results for named preset scans.
    """
    params = {
        "direction": "all",
        "min_confidence": 0.0,
        "max_confidence": 100.0,
        "volatility": "all",
        "sector": "all",
        "min_rsi": 0.0,
        "max_rsi": 100.0,
        "min_market_cap": 0.0,
        "sort_by": "confidence",
        "sort_dir": "desc"
    }
    
    desc = ""
    
    if preset_name == "high_confidence_buys":
        params["direction"] = "strong_up" # Or up, but endpoint params only support exact match. We will fetch and filter in memory for multiple.
        desc = "ST-GCN predicts up/strong_up with >75% confidence"
    elif preset_name == "oversold_bounces":
        params["max_rsi"] = 30.0
        desc = "RSI below 30 with bullish prediction — potential reversals"
    elif preset_name == "volatility_breakouts":
        params["direction"] = "strong_up"
        desc = "Extreme volatility with strong buy signal — high risk/reward"
    elif preset_name == "defi_opportunities":
        params["sector"] = "defi"
        params["min_confidence"] = 0.60
        desc = "DeFi sector assets with bullish signals"
    elif preset_name == "large_cap_only":
        params["min_market_cap"] = 10000000000
        desc = "Market cap >$10B — lower risk signals"
    elif preset_name == "contrarian_signals":
        params["direction"] = "strong_up"
        params["volatility"] = "extreme"
        desc = "Extreme volatility buy signals — against the trend"
    else:
        return {"error": "Unknown preset"}
        
    # Since the params router expects single direction but some presets want "up or strong_up",
    # we manually call the logic here with custom filtering for presets.
    
    assets = db.query(Asset).all()
    preds = db.query(Prediction).order_by(desc(Prediction.predicted_at)).limit(2000).all()
    latest_preds = {p.asset_id: p for p in preds}
    
    # Get latest technical features for all assets in one batched query (No N+1)
    tech_query = """
        SELECT asset_id, rsi_14, macd, returns_1d, returns_7d, volatility_7d 
        FROM technical_features 
        WHERE (asset_id, timestamp) IN (
            SELECT asset_id, MAX(timestamp) 
            FROM technical_features 
            GROUP BY asset_id
        )
    """
    tech_results = db.execute(text(tech_query)).fetchall()
    latest_tech = {t[0]: {"rsi_14": t[1], "macd": t[2], "returns_1d": t[3], "returns_7d": t[4], "volatility_7d": t[5]} for t in tech_results}
    
    results = []
    for a in assets:
        t_data = latest_tech.get(a.id, {})
        t_rsi = t_data.get("rsi_14", 50.0)
        t_macd = t_data.get("macd", 0.0)
        
        t_ret1d = t_data.get("returns_1d", None)
        if t_ret1d is None or t_ret1d == 0.0:
            pct_change = a.price_change_24h_pct or 0.0
        else:
            pct_change = t_ret1d * 100
            
        t_ret7d = t_data.get("returns_7d", 0.0)
        t_vol7d = t_data.get("volatility_7d", 0.0)
        
        pred = latest_preds.get(a.id)
        # Use defaults if prediction is missing
        if pred:
            p_dir = pred.direction or "neutral"
            p_conf = pred.confidence or 0.0
            p_vol = get_volatility_regime(t_vol7d)
            pred_time = pred.predicted_at.isoformat() if pred.predicted_at else None
        else:
            p_dir = "neutral"
            p_conf = 0.0
            p_vol = get_volatility_regime(t_vol7d)
            pred_time = None
            
        a_sec = a.sector or "other"
        
        a_mcap = a.market_cap_usd or 0.0
        
        # Apply Preset Logic
        keep = True
        
        if preset_name == "high_confidence_buys":
            if p_dir not in ["up", "strong_up"]: keep = False
            if p_conf < 75.0: keep = False
        elif preset_name == "oversold_bounces":
            if t_rsi > 30.0: keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
        elif preset_name == "volatility_breakouts":
            if p_vol not in ["high", "extreme"]: keep = False
            if p_dir != "strong_up": keep = False
        elif preset_name == "defi_opportunities":
            if a_sec != "defi": keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
            if p_conf < 60.0: keep = False
        elif preset_name == "large_cap_only":
            if a_mcap < 10000000000: keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
        elif preset_name == "contrarian_signals":
            if p_dir != "strong_up": keep = False
            if p_vol != "extreme": keep = False
            
        if not keep:
            continue
            
        # Check live cache for current price
        live_cache = LIVE_OHLCV_CACHE.get(a.symbol)
        c_price = live_cache[-1]["close"] if live_cache else (a.current_price or 0.0)
        
        # Skip coins that have $0 balance (delisted, missing data)
        if c_price <= 0.0:
            continue
            
        record = {
            "symbol": a.symbol,
            "name": a.name,
            "sector": a_sec,
            "market_cap_usd": a_mcap,
            "current_price": c_price,
            "price_change_24h_pct": pct_change,
            "direction": p_dir,
            "confidence": p_conf,
            "volatility_regime": p_vol,
            "rsi_14": t_rsi,
            "macd": t_macd,
            "returns_1d": t_ret1d,
            "returns_7d": t_ret7d,
            "volatility_7d": t_vol7d,
            "predicted_at": pred_time
        }
        results.append(record)
        
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return {
        "preset_name": preset_name,
        "description": desc,
        "count": len(results),
        "results": results
    }

def calculate_rsi_live(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Wilder's Smoothing Method
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd_live(series: pd.Series) -> tuple[float, float]:
    ema_12 = series.ewm(span=12, adjust=False).mean()
    ema_26 = series.ewm(span=26, adjust=False).mean()
    macd_series = ema_12 - ema_26
    signal_series = macd_series.ewm(span=9, adjust=False).mean()
    return float(macd_series.iloc[-1]), float(signal_series.iloc[-1])

@router.post("/refresh")
def refresh_live_technicals(db: Session = Depends(get_db)):
    """
    Actively fetches live tick data from Binance for all assets using CCXT,
    calculates real-time 14-day RSI and 7-day returns, and updates the database.
    """
    assets = db.query(Asset).all()
    if not assets:
        return {"status": "error", "message": "No assets found"}
        
    exchange = ccxt.binance({'enableRateLimit': False})
    
    def fetch_ohlcv(sym):
        try:
            # Fetch 1500 hours (60 days) to match individual coin pages exactly
            data = exchange.fetch_ohlcv(f"{sym}/USDT", "1h", limit=1500)
            if not data or len(data) < 24: return sym, None
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
            return sym, df
        except:
            return sym, None

    timestamp_now = datetime.utcnow().isoformat()
    updated_records = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_ohlcv, [a.symbol for a in assets])
        
    symbol_to_id = {a.symbol: a.id for a in assets}
    
    for sym, asset_df in results:
        if asset_df is None: continue
        
        closes = asset_df["close"]
        rsi_series = calculate_rsi_live(closes, 14)
        latest_rsi = float(rsi_series.iloc[-1])
        if np.isnan(latest_rsi): continue
        
        # 1-day return is pct change between the latest close and the close 24 rows ago (since interval is 1h)
        ret1d = float(closes.pct_change(24).iloc[-1])
        ret7d = float(closes.pct_change(24*7).iloc[-1]) if len(closes) > 24*7 else 0.0
        vol7d = float(closes.pct_change(1).rolling(24*7).std().iloc[-1]) if len(closes) > 24*7 else 0.0
        
        if np.isnan(ret1d): ret1d = 0.0
        if np.isnan(ret7d): ret7d = 0.0
        if np.isnan(vol7d): vol7d = 0.0
        
        try:
            macd_val, macd_sig = calculate_macd_live(closes)
            if np.isnan(macd_val): macd_val = 0.0
            if np.isnan(macd_sig): macd_sig = 0.0
        except:
            macd_val = 0.0
            macd_sig = 0.0
        
        db.execute(text("""
            INSERT INTO technical_features 
            (asset_id, timestamp, rsi_14, returns_1d, returns_7d, volatility_7d, macd, macd_signal, atr_14, bb_width)
            VALUES (:asset_id, :timestamp, :rsi_14, :ret1d, :ret7d, :vol7d, :macd, :macd_sig, 0.0, 0.0)
            ON CONFLICT(asset_id, timestamp) DO UPDATE SET
                rsi_14=excluded.rsi_14,
                returns_1d=excluded.returns_1d,
                returns_7d=excluded.returns_7d,
                volatility_7d=excluded.volatility_7d,
                macd=excluded.macd,
                macd_signal=excluded.macd_signal
        """), {
            "asset_id": symbol_to_id[sym], "timestamp": timestamp_now,
            "rsi_14": latest_rsi, "ret1d": ret1d, "ret7d": ret7d, "vol7d": vol7d,
            "macd": macd_val, "macd_sig": macd_sig
        })
        updated_records += 1
        
    db.commit()
    return {"status": "success", "message": f"Refreshed live technicals for {updated_records} assets"}

