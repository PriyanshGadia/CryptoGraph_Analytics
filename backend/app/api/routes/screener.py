from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from datetime import datetime, timezone
from app.core.cache import cached

router = APIRouter(prefix="/screener", tags=["screener"])

@router.get("/")
@cached(ttl_seconds=300)
def screen_assets(
    direction: str = "all",        # all,strong_up,up,neutral,down,strong_down
    min_confidence: float = 0.0,   # 0.0 to 1.0
    max_confidence: float = 1.0,
    volatility: str = "all",       # all,low,medium,high,extreme
    sector: str = "all",           # all,layer1,defi,exchange,payment,gaming,privacy,storage,other
    min_rsi: float = 0.0,
    max_rsi: float = 100.0,
    min_market_cap: float = 0.0,
    sort_by: str = "confidence",   # confidence,market_cap,returns_1d,volatility_7d,rsi_14
    sort_dir: str = "desc",        # asc,desc
    db=Depends(get_supabase)
):
    """
    Returns filtered and sorted list of assets.
    """
    # 1. Get all assets
    assets_res = db.table("assets").select("*").execute()
    asset_list = assets_res.data
    
    # We need predictions and technical features.
    # To optimize, we'll fetch the latest prediction for each asset
    # and the latest technical_feature for each asset.
    # Supabase lacks DISTINCT ON easily, so we fetch last N days or order by desc and take first manually.
    
    # Get latest predictions
    preds_res = db.table("predictions").select("*").order("timestamp", desc=True).limit(2000).execute()
    latest_preds = {}
    for p in preds_res.data:
        aid = p["asset_id"]
        if aid not in latest_preds:
            latest_preds[aid] = p
            
    # Get latest technical features
    tech_res = db.table("technical_features").select("*").order("timestamp", desc=True).limit(2000).execute()
    latest_techs = {}
    for t in tech_res.data:
        aid = t["asset_id"]
        if aid not in latest_techs:
            latest_techs[aid] = t
            
    # Apply filters
    results = []
    for a in asset_list:
        aid = a["id"]
        pred = latest_preds.get(aid, {})
        tech = latest_techs.get(aid, {})
        
        # Values
        p_dir = pred.get("direction", "neutral")
        p_conf = pred.get("confidence", 0.0)
        p_vol = pred.get("volatility_regime", "medium")
        a_sec = a.get("sector", "other")
        t_rsi = tech.get("rsi_14", 50.0)
        a_mcap = a.get("market_cap_usd", 0.0) or 0.0
        
        # Check filters
        if direction != "all" and p_dir != direction: continue
        if p_conf < min_confidence or p_conf > max_confidence: continue
        if volatility != "all" and p_vol != volatility: continue
        if sector != "all" and a_sec != sector: continue
        if t_rsi < min_rsi or t_rsi > max_rsi: continue
        if a_mcap < min_market_cap: continue
        
        # Build record
        record = {
            "symbol": a.get("symbol"),
            "name": a.get("name"),
            "sector": a_sec,
            "market_cap_usd": a_mcap,
            "current_price": a.get("current_price"),
            "price_change_24h_pct": a.get("price_change_24h_pct"),
            "direction": p_dir,
            "confidence": p_conf,
            "volatility_regime": p_vol,
            "rsi_14": t_rsi,
            "macd": tech.get("macd"),
            "returns_1d": tech.get("returns_1d"),
            "returns_7d": tech.get("returns_7d"),
            "volatility_7d": tech.get("volatility_7d"),
            "predicted_at": pred.get("predicted_at")
        }
        results.append(record)
        
    # Sort
    # handle None values in sort keys safely
    reverse = (sort_dir == "desc")
    def safe_sort_key(item):
        val = item.get(sort_by)
        if val is None:
            return -float('inf') if reverse else float('inf')
        return val
        
    results.sort(key=safe_sort_key, reverse=reverse)
    
    return results

@router.get("/presets/{preset_name}")
@cached(ttl_seconds=300)
def get_preset_scan(preset_name: str, db=Depends(get_supabase)):
    """
    Returns results for named preset scans.
    """
    params = {
        "direction": "all",
        "min_confidence": 0.0,
        "max_confidence": 1.0,
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
    
    assets_res = db.table("assets").select("*").execute()
    preds_res = db.table("predictions").select("*").order("timestamp", desc=True).limit(2000).execute()
    latest_preds = {p["asset_id"]: p for p in preds_res.data}
    tech_res = db.table("technical_features").select("*").order("timestamp", desc=True).limit(2000).execute()
    latest_techs = {t["asset_id"]: t for t in tech_res.data}
    
    results = []
    for a in assets_res.data:
        aid = a["id"]
        pred = latest_preds.get(aid, {})
        tech = latest_techs.get(aid, {})
        
        p_dir = pred.get("direction", "neutral")
        p_conf = pred.get("confidence", 0.0)
        p_vol = pred.get("volatility_regime", "medium")
        a_sec = a.get("sector", "other")
        t_rsi = tech.get("rsi_14", 50.0)
        a_mcap = a.get("market_cap_usd", 0.0) or 0.0
        
        # Apply Preset Logic
        keep = True
        
        if preset_name == "high_confidence_buys":
            if p_dir not in ["up", "strong_up"]: keep = False
            if p_conf < 0.75: keep = False
        elif preset_name == "oversold_bounces":
            if t_rsi > 30.0: keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
        elif preset_name == "volatility_breakouts":
            if p_vol not in ["high", "extreme"]: keep = False
            if p_dir != "strong_up": keep = False
        elif preset_name == "defi_opportunities":
            if a_sec != "defi": keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
            if p_conf < 0.60: keep = False
        elif preset_name == "large_cap_only":
            if a_mcap < 10000000000: keep = False
            if p_dir not in ["up", "strong_up"]: keep = False
        elif preset_name == "contrarian_signals":
            if p_dir != "strong_up": keep = False
            if p_vol != "extreme": keep = False
            
        if not keep:
            continue
            
        record = {
            "symbol": a.get("symbol"),
            "name": a.get("name"),
            "sector": a_sec,
            "market_cap_usd": a_mcap,
            "current_price": a.get("current_price"),
            "price_change_24h_pct": a.get("price_change_24h_pct"),
            "direction": p_dir,
            "confidence": p_conf,
            "volatility_regime": p_vol,
            "rsi_14": t_rsi,
            "macd": tech.get("macd"),
            "returns_1d": tech.get("returns_1d"),
            "returns_7d": tech.get("returns_7d"),
            "volatility_7d": tech.get("volatility_7d"),
            "predicted_at": pred.get("predicted_at")
        }
        results.append(record)
        
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return {
        "preset_name": preset_name,
        "description": desc,
        "count": len(results),
        "results": results
    }
    return result
