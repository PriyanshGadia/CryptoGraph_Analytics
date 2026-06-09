from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from datetime import datetime, timezone, timedelta
from app.core.cache import cached

router = APIRouter(prefix="/sentiment-data", tags=["sentiment"])

@router.get("/fear-greed-history")
@cached(ttl_seconds=300)
def get_fear_greed_history(days: int = 365, db=Depends(get_supabase)):
    """
    Returns fear & greed history for chart.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    # We use BTC as the proxy for market fear & greed
    assets_res = db.table("assets").select("id").eq("symbol", "BTC").execute()
    if not assets_res.data:
        return []
        
    btc_id = assets_res.data[0]["id"]
    
    res = db.table("sentiment").select("timestamp, fear_greed")\
        .eq("asset_id", btc_id)\
        .gte("timestamp", since.isoformat())\
        .order("timestamp", desc=False)\
        .execute()
        
    data = []
    for r in res.data:
        fg = r.get("fear_greed")
        if fg is None:
            continue
            
        if fg <= 24: label = "Extreme Fear"
        elif fg <= 44: label = "Fear"
        elif fg <= 55: label = "Neutral"
        elif fg <= 74: label = "Greed"
        else: label = "Extreme Greed"
            
        data.append({
            "date": r["timestamp"].split("T")[0],
            "fear_greed": fg,
            "label": label
        })
        
    return data

@router.get("/fear-greed-vs-btc")
@cached(ttl_seconds=300)
def get_fear_greed_vs_btc(days: int = 365, db=Depends(get_supabase)):
    """
    Returns combined fear_greed and BTC close price for dual-axis chart.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    assets_res = db.table("assets").select("id").eq("symbol", "BTC").execute()
    if not assets_res.data:
        return []
        
    btc_id = assets_res.data[0]["id"]
    
    # Get sentiment
    sent_res = db.table("sentiment").select("timestamp, fear_greed")\
        .eq("asset_id", btc_id)\
        .gte("timestamp", since.isoformat())\
        .execute()
        
    fg_map = {r["timestamp"].split("T")[0]: r["fear_greed"] for r in sent_res.data if r.get("fear_greed") is not None}
    
    # Get OHLCV
    ohlcv_res = db.table("ohlcv").select("timestamp, close")\
        .eq("asset_id", btc_id)\
        .gte("timestamp", since.isoformat())\
        .order("timestamp", desc=False)\
        .execute()
        
    data = []
    prev_close = None
    for r in ohlcv_res.data:
        date_str = r["timestamp"].split("T")[0]
        fg = fg_map.get(date_str)
        close = r["close"]
        ret = (close - prev_close) / prev_close if prev_close else 0.0
        prev_close = close
        
        if fg is not None:
            data.append({
                "date": date_str,
                "fear_greed": fg,
                "btc_price": close,
                "btc_return_1d": ret
            })
            
    return data

@router.get("/sector-sentiment")
@cached(ttl_seconds=300)
def get_sector_sentiment(db=Depends(get_supabase)):
    """
    Returns average current sentiment by sector.
    """
    assets_res = db.table("assets").select("id, sector").execute()
    asset_sector_map = {a["id"]: a.get("sector", "other") for a in assets_res.data}
    
    # We only need the latest sentiment row per asset
    # Supabase doesn't easily do SELECT DISTINCT ON, so we query the last 7 days and group
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    
    sent_res = db.table("sentiment").select("asset_id, timestamp, sentiment_score, community_score, public_interest")\
        .gte("timestamp", since.isoformat())\
        .order("timestamp", desc=True)\
        .execute()
        
    latest_sent = {}
    for r in sent_res.data:
        aid = r["asset_id"]
        # Only keep the first one we see (which is the latest due to desc sort)
        if aid not in latest_sent and r.get("sentiment_score") is not None:
            latest_sent[aid] = r
            
    sector_aggs = {}
    for aid, s in latest_sent.items():
        sector = asset_sector_map.get(aid, "other")
        if sector not in sector_aggs:
            sector_aggs[sector] = {"sent_sum": 0, "comm_sum": 0, "pub_sum": 0, "count": 0}
            
        sector_aggs[sector]["sent_sum"] += (s.get("sentiment_score") or 0)
        sector_aggs[sector]["comm_sum"] += (s.get("community_score") or 0)
        sector_aggs[sector]["pub_sum"] += (s.get("public_interest") or 0)
        sector_aggs[sector]["count"] += 1
        
    results = []
    for sector, aggs in sector_aggs.items():
        count = aggs["count"]
        if count > 0:
            results.append({
                "sector": sector,
                "avg_sentiment": aggs["sent_sum"] / count,
                "avg_community": aggs["comm_sum"] / count,
                "avg_public_interest": aggs["pub_sum"] / count,
                "asset_count": count
            })
            
    # Sort by avg_sentiment descending
    results.sort(key=lambda x: x["avg_sentiment"], reverse=True)
    return results

@router.get("/trending")
@cached(ttl_seconds=300)
def get_trending_assets(db=Depends(get_supabase)):
    """
    Returns assets with biggest sentiment changes (gainers and losers).
    """
    assets_res = db.table("assets").select("id, symbol, sector").execute()
    asset_map = {a["id"]: a for a in assets_res.data}
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=14) # Give buffer to find older row
    
    sent_res = db.table("sentiment").select("asset_id, timestamp, sentiment_score")\
        .gte("timestamp", since.isoformat())\
        .order("timestamp", desc=True)\
        .execute()
        
    # Group by asset
    asset_sentiments = {}
    for r in sent_res.data:
        aid = r["asset_id"]
        if r.get("sentiment_score") is None:
            continue
        if aid not in asset_sentiments:
            asset_sentiments[aid] = []
        asset_sentiments[aid].append(r)
        
    changes = []
    for aid, rows in asset_sentiments.items():
        if len(rows) < 2:
            continue
            
        # Rows are sorted desc by timestamp, so [0] is latest
        latest = rows[0]
        
        # Find row closest to 7 days ago
        target_date = datetime.fromisoformat(latest["timestamp"]) - timedelta(days=7)
        older = rows[-1] # default to oldest
        best_diff = float("inf")
        
        for r in rows[1:]:
            r_date = datetime.fromisoformat(r["timestamp"])
            diff = abs((r_date - target_date).total_seconds())
            if diff < best_diff:
                best_diff = diff
                older = r
                
        current_score = latest["sentiment_score"]
        prev_score = older["sentiment_score"]
        change = current_score - prev_score
        
        asset = asset_map.get(aid, {})
        changes.append({
            "symbol": asset.get("symbol"),
            "sector": asset.get("sector"),
            "current_sentiment": current_score,
            "prev_sentiment": prev_score,
            "change": change
        })
        
    changes.sort(key=lambda x: x["change"], reverse=True)
    
    gainers = changes[:5]
    losers = changes[-5:]
    losers.sort(key=lambda x: x["change"]) # most negative first
    
    result = {
        "gainers": gainers,
        "losers": losers
    }
    return result
