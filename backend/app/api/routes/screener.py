from fastapi import APIRouter, Depends
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from typing import List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import ccxt
import concurrent.futures
from app.db.models import Asset
from app.core.cache import cached
from app.core.streams.binance_ws import get_global_market_state

router = APIRouter(prefix="/screener", tags=["screener"])

@router.get("/")
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
):
    """
    Returns filtered and sorted list of assets from SSOT state.
    """
    state = get_global_market_state()
    
    all_vols = [d.get("volatility_7d", 0.0) for d in state.values()]
    if len(all_vols) > 0:
        vol_thresholds = np.percentile(all_vols, [25, 50, 75, 90])
    else:
        vol_thresholds = [0.02, 0.035, 0.05, 0.065]
    
    results = []
    for sym, data in state.items():
        # Apply filters
        if direction != "all" and data.get("predicted_direction", "neutral") != direction: continue
        conf = data.get("confidence", 0.0)
        if conf < min_confidence or conf > max_confidence: continue
        
        # Calculate dynamic volatility regime
        v = data.get("volatility_7d", 0.0)
        p_vol = "low"
        if v > vol_thresholds[3]: p_vol = "extreme"
        elif v > vol_thresholds[2]: p_vol = "high"
        elif v > vol_thresholds[1]: p_vol = "medium"
            
        if volatility != "all" and p_vol != volatility: continue
        if sector != "all" and data.get("sector", "other") != sector: continue
        rsi = data.get("rsi_14", 50.0)
        if rsi < min_rsi or rsi > max_rsi: continue
        if data.get("market_cap_usd", 0.0) < min_market_cap: continue
        
        record = {
            "symbol": sym,
            "name": data.get("name", sym),
            "sector": data.get("sector", "other"),
            "market_cap_usd": data.get("market_cap_usd", 0.0),
            "volume_24h": data.get("volume_24h", 0.0),
            "current_price": data.get("current_price", 0.0),
            "price_change_24h_pct": data.get("price_change_24h_pct", 0.0),
            "predicted_direction": data.get("predicted_direction", "neutral"),
            "confidence": conf,
            "volatility_regime": p_vol,
            "rsi_14": rsi,
            "macd": data.get("macd", 0.0),
            "returns_1d": data.get("price_change_24h_pct", 0.0) / 100.0,
            "returns_7d": data.get("returns_7d", 0.0),
            "volatility_7d": v,
            "predicted_at": None # Optional
        }
        results.append(record)
        
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
def get_preset_scan(preset_name: str):
    """
    Returns results for named preset scans using SSOT state.
    """
    state = get_global_market_state()
    desc_text = ""
    
    all_vols = [d.get("volatility_7d", 0.0) for d in state.values()]
    if len(all_vols) > 0:
        vol_thresholds = np.percentile(all_vols, [25, 50, 75, 90])
    else:
        vol_thresholds = [0.02, 0.035, 0.05, 0.065]
        
    if preset_name == "high_confidence_buys":
        desc_text = "ST-GCN predicts up/strong_up with >75% confidence"
    elif preset_name == "oversold_bounces":
        desc_text = "RSI below 30 with bullish prediction — potential reversals"
    elif preset_name == "volatility_breakouts":
        desc_text = "Extreme volatility with strong buy signal — high risk/reward"
    elif preset_name == "defi_opportunities":
        desc_text = "DeFi sector assets with bullish signals"
    elif preset_name == "large_cap_only":
        desc_text = "Market cap >$10B — lower risk signals"
    elif preset_name == "contrarian_signals":
        desc_text = "Extreme volatility buy signals — against the trend"
    else:
        return {"error": "Unknown preset"}
        
    results = []
    for sym, data in state.items():
        p_dir = data.get("predicted_direction", "neutral")
        p_conf = data.get("confidence", 0.0)
        t_rsi = data.get("rsi_14", 50.0)
        a_sec = data.get("sector", "other")
        a_mcap = data.get("market_cap_usd", 0.0)
        v = data.get("volatility_7d", 0.0)
        p_vol = "low"
        if v > vol_thresholds[3]: p_vol = "extreme"
        elif v > vol_thresholds[2]: p_vol = "high"
        elif v > vol_thresholds[1]: p_vol = "medium"


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
            
        record = {
            "symbol": sym,
            "name": data.get("name", sym),
            "sector": a_sec,
            "market_cap_usd": a_mcap,
            "volume_24h": data.get("volume_24h", 0.0),
            "current_price": data.get("current_price", 0.0),
            "price_change_24h_pct": data.get("price_change_24h_pct", 0.0),
            "predicted_direction": p_dir,
            "confidence": p_conf,
            "volatility_regime": p_vol,
            "rsi_14": t_rsi,
            "macd": data.get("macd", 0.0),
            "returns_1d": data.get("price_change_24h_pct", 0.0) / 100.0,
            "returns_7d": data.get("returns_7d", 0.0),
            "volatility_7d": v,
            "predicted_at": None
        }
        results.append(record)
        
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return {
        "preset_name": preset_name,
        "description": desc_text,
        "count": len(results),
        "results": results
    }

def calculate_rsi_live(series: pd.Series, period: int = 14) -> pd.Series:
    from ml.data.feature_engineering.technical_indicators import compute_rsi
    return compute_rsi(series, length=period)

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
            data = exchange.fetch_ohlcv(f"{sym}/USDT", "1h", limit=1500)
            if not data or len(data) < 24: return sym, None
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
            return sym, df
        except Exception:
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
        
        ret1d = float(np.log(closes / closes.shift(24)).iloc[-1]) if len(closes) > 24 else 0.0
        ret7d = float(np.log(closes / closes.shift(24*7)).iloc[-1]) if len(closes) > 24*7 else 0.0
        vol7d = float(np.log(closes / closes.shift(1)).rolling(24*7).std().iloc[-1]) if len(closes) > 24*7 else 0.0
        
        if np.isnan(ret1d): ret1d = 0.0
        if np.isnan(ret7d): ret7d = 0.0
        if np.isnan(vol7d): vol7d = 0.0
        
        try:
            macd_val, macd_sig = calculate_macd_live(closes)
            if np.isnan(macd_val): macd_val = 0.0
            if np.isnan(macd_sig): macd_sig = 0.0
        except Exception:
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

