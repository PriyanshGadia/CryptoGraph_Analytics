"""Risk dashboard routes."""
from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from datetime import datetime, timezone, timedelta
from app.core.cache import cached
import numpy as np
import pandas as pd

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("")
async def get_risk_data(db=Depends(get_supabase)):
    """Returns full risk dashboard data."""

    # 1. Get latest predictions for all assets
    preds_res = (db.table("predictions")
        .select("asset_id, direction, confidence, volatility_regime")
        .order("predicted_at", desc=True)
        .limit(200)
        .execute())
    preds = preds_res.data or []

    # Deduplicate: keep only latest per asset_id
    seen: set = set()
    latest_preds: list = []
    for p in preds:
        if p["asset_id"] not in seen:
            seen.add(p["asset_id"])
            latest_preds.append(p)

    # 2. Compute market regime
    up_count = sum(1 for p in latest_preds if p["direction"] in ["up", "strong_up"])
    down_count = sum(1 for p in latest_preds if p["direction"] in ["down", "strong_down"])
    total = len(latest_preds) or 1

    if up_count / total > 0.6:
        regime = "bull"
    elif down_count / total > 0.6:
        regime = "bear"
    else:
        regime = "sideways"

    # 3. Get average volatility from technical_features
    vol_res = (db.table("technical_features")
        .select("volatility_7d")
        .order("timestamp", desc=True)
        .limit(50)
        .execute())
    vol_values = [r["volatility_7d"] for r in (vol_res.data or [])
                  if r.get("volatility_7d") is not None]
    avg_vol = (sum(vol_values) / len(vol_values) * 100) if vol_values else 0.0

    # 4. Get correlation clusters from graph_snapshots
    graph_res = (db.table("graph_snapshots")
        .select("source_asset, target_asset, weight")
        .order("timestamp", desc=True)
        .limit(500)
        .execute())

    # Build adjacency and find connected components (union-find)
    parent: dict = {}

    def find(x: str) -> str:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for edge in (graph_res.data or []):
        if edge.get("weight", 0) > 0.6:
            union(str(edge["source_asset"]), str(edge["target_asset"]))

    # Map asset_id to symbol
    assets_res = db.table("assets").select("id,symbol,sector").execute()
    id_to_sym = {a["id"]: a["symbol"] for a in (assets_res.data or [])}

    clusters: dict = {}
    for asset_id in id_to_sym:
        root = find(asset_id)
        clusters.setdefault(root, []).append(id_to_sym[asset_id])

    # Filter to clusters with >1 member
    named_clusters: dict = {}
    cluster_num = 1
    for _root, syms in clusters.items():
        if len(syms) > 1:
            named_clusters[f"cluster_{cluster_num}"] = sorted(syms)
            cluster_num += 1

    # 5. Top movers from technical_features
    tech_res = (db.table("technical_features")
        .select("asset_id, returns_1d, volatility_7d")
        .order("timestamp", desc=True)
        .limit(100)
        .execute())

    seen_assets: set = set()
    movers: list = []
    for r in (tech_res.data or []):
        aid = r["asset_id"]
        if aid not in seen_assets and r.get("volatility_7d") is not None:
            seen_assets.add(aid)
            movers.append({
                "symbol":        id_to_sym.get(aid, "?"),
                "returns_1d":    round(r.get("returns_1d") or 0, 6),
                "volatility_7d": round(r.get("volatility_7d") or 0, 6)
            })

    top_movers = sorted(movers, key=lambda x: abs(x["volatility_7d"]), reverse=True)[:5]

    # 6. Risk alerts
    alerts: list = []
    graph_weights = [e.get("weight", 0) for e in (graph_res.data or [])]
    avg_weight = sum(graph_weights) / len(graph_weights) if graph_weights else 0
    if avg_weight > 0.8:
        alerts.append("High correlation spike - assets moving in lockstep")
    if any(p.get("volatility_regime") == "extreme" for p in latest_preds):
        alerts.append("Extreme volatility detected in one or more assets")

    # Get latest fear & greed
    fg_res = (db.table("sentiment")
        .select("fear_greed")
        .not_.is_("fear_greed", "null")
        .order("timestamp", desc=True)
        .limit(1)
        .execute())
    if fg_res.data:
        fg = fg_res.data[0]["fear_greed"]
        if fg < 20:
            alerts.append(f"Extreme Fear - Fear & Greed Index at {fg}")
        if fg > 80:
            alerts.append(f"Extreme Greed - Fear & Greed Index at {fg}")

    return {
        "market_regime":        regime,
        "average_volatility":   round(avg_vol, 4),
        "correlation_clusters": named_clusters,
        "top_movers":           top_movers,
        "risk_alerts":          alerts,
        "up_pct":               round(up_count / total * 100, 1),
        "down_pct":             round(down_count / total * 100, 1),
    }

@router.get("/macro")
@cached(ttl_seconds=300)
def get_macro_data(db=Depends(get_supabase)):
    """
    Returns macro economic indicators for dashboard.
    """
    now = datetime.now(timezone.utc)
    since_2y = now - timedelta(days=730)
    
    # 1. Query last 730 days
    macro_res = db.table("macro_indicators")\
        .select("timestamp, fed_rate, cpi, inflation, vix, fed_rate_z, cpi_z, inflation_z, vix_z")\
        .gte("timestamp", since_2y.isoformat())\
        .order("timestamp", desc=False)\
        .execute()
        
    history = macro_res.data or []
    
    # Defaults
    current_fed_rate = 0.0
    current_cpi = 0.0
    current_inflation = 0.0
    current_vix = 0.0
    fed_rate_trend = "stable"
    vix_regime = "normal"
    correlation = 0.0
    
    if history:
        latest = history[-1]
        current_fed_rate = latest.get("fed_rate") or 0.0
        current_cpi = latest.get("cpi") or 0.0
        current_inflation = latest.get("inflation") or 0.0
        current_vix = latest.get("vix") or 0.0
        
        # Trend based on 30 days ago
        since_30d = now - timedelta(days=30)
        past_res = db.table("macro_indicators")\
            .select("fed_rate")\
            .lte("timestamp", since_30d.isoformat())\
            .order("timestamp", desc=True)\
            .limit(1)\
            .execute()
            
        if past_res.data:
            past_rate = past_res.data[0].get("fed_rate") or current_fed_rate
            if past_rate > 0:
                diff = (current_fed_rate - past_rate) / past_rate
                if diff > 0.05:
                    fed_rate_trend = "rising"
                elif diff < -0.05:
                    fed_rate_trend = "falling"
                    
        # VIX regime
        if current_vix < 15:
            vix_regime = "low"
        elif current_vix <= 25:
            vix_regime = "normal"
        elif current_vix <= 35:
            vix_regime = "fear"
        else:
            vix_regime = "panic"
            
        # Crypto-VIX correlation (90 days)
        since_90d = now - timedelta(days=90)
        
        # Get BTC returns
        btc_res = db.table("assets").select("id").eq("symbol", "BTC").execute()
        if btc_res.data:
            btc_id = btc_res.data[0]["id"]
            tech_res = db.table("technical_features")\
                .select("timestamp, returns_1d")\
                .eq("asset_id", btc_id)\
                .gte("timestamp", since_90d.isoformat())\
                .execute()
                
            if tech_res.data:
                vix_90d = [r for r in history if r["timestamp"] >= since_90d.isoformat()]
                vix_df = pd.DataFrame(vix_90d)
                tech_df = pd.DataFrame(tech_res.data)
                
                if not vix_df.empty and not tech_df.empty:
                    vix_df["date"] = pd.to_datetime(vix_df["timestamp"]).dt.date
                    tech_df["date"] = pd.to_datetime(tech_df["timestamp"]).dt.date
                    
                    merged = pd.merge(vix_df, tech_df, on="date", how="inner")
                    if len(merged) > 5:
                        c = merged["vix"].corr(merged["returns_1d"])
                        if not np.isnan(c):
                            correlation = float(c)
                            
    return {
        "history": history,
        "current_fed_rate": current_fed_rate,
        "fed_rate_trend": fed_rate_trend,
        "current_cpi": current_cpi,
        "current_inflation": current_inflation,
        "current_vix": current_vix,
        "vix_regime": vix_regime,
        "crypto_vix_correlation": correlation
    }
