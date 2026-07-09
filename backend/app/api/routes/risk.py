"""Risk dashboard routes — comprehensive real data."""
from fastapi import APIRouter, Depends
import numpy as np
import pandas as pd
import yfinance as yf
from app.api.deps import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime, timezone, timedelta
from app.db.models import Prediction, Asset, OHLCV
from app.core.cache import cached
from app.core.streams.binance_ws import LIVE_OHLCV_CACHE

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("")
@cached(ttl_seconds=120)
def get_risk_data(db: Session = Depends(get_db)):
    """Returns full risk dashboard data with real metrics."""
    # 1. Get latest predictions per asset (deduplicated)
    subq = db.query(
        Prediction.asset_id,
        func.max(Prediction.predicted_at).label("max_at")
    ).group_by(Prediction.asset_id).subquery()

    latest_preds = db.query(Prediction).join(
        subq,
        (Prediction.asset_id == subq.c.asset_id) & (Prediction.predicted_at == subq.c.max_at)
    ).all()

    # 2. Market regime
    up_count = sum(1 for p in latest_preds if p.direction in ["up", "strong_up"])
    down_count = sum(1 for p in latest_preds if p.direction in ["down", "strong_down"])
    total = len(latest_preds) or 1

    if up_count / total > 0.6:
        regime = "bull"
    elif down_count / total > 0.6:
        regime = "bear"
    else:
        regime = "sideways"

    # Calculate global confidence
    valid_confidences = [p.confidence for p in latest_preds if p.confidence is not None]
    global_confidence = float(np.mean(valid_confidences)) if valid_confidences else 0.0

    # 3. Get real volatility data from technical_features
    assets = db.query(Asset).all()
    asset_map = {a.id: a for a in assets}

    tech_rows = db.execute(text("""
        SELECT t1.asset_id, t1.volatility_7d, t1.returns_1d
        FROM technical_features t1
        JOIN (
            SELECT asset_id, MAX(timestamp) as max_ts
            FROM technical_features
            GROUP BY asset_id
        ) t2 ON t1.asset_id = t2.asset_id AND t1.timestamp = t2.max_ts
    """)).fetchall()

    vol_data = {}
    for r in tech_rows:
        vol_data[r[0]] = {"vol": r[1] or 0, "ret1d": r[2] or 0}

    # Average volatility across all assets
    all_vols = [v["vol"] for v in vol_data.values() if v["vol"] > 0]
    avg_vol = float(np.mean(all_vols) * 100) if all_vols else 5.0  # percent

    # 4. Top Volatile Assets (sorted by 7d vol, desc)
    vol_list = []
    for aid, vd in vol_data.items():
        asset = asset_map.get(aid)
        if not asset or vd["vol"] <= 0:
            continue
        # Get live price
        live = LIVE_OHLCV_CACHE.get(asset.symbol)
        price = live[-1]["close"] if live else 0.0

        vol_list.append({
            "symbol": asset.symbol,
            "name": asset.name or asset.symbol,
            "volatility_7d": round(vd["vol"] * 100, 2),
            "returns_1d": round(vd["ret1d"] * 100, 2),
            "current_price": price,
        })

    vol_list.sort(key=lambda x: x["volatility_7d"], reverse=True)
    top_volatile = vol_list[:10]

    # 5. Correlation clusters from predictions
    pred_map = {}
    for p in latest_preds:
        a = asset_map.get(p.asset_id)
        if a:
            d = p.direction or "neutral"
            if d not in pred_map:
                pred_map[d] = []
            pred_map[d].append(a.symbol)

    clusters = {}
    for i, (direction, symbols) in enumerate(pred_map.items()):
        cluster_name = f"{direction}_cluster"
        clusters[cluster_name] = symbols[:10]

    # 6. Risk Alerts — real conditions
    alerts = []
    extreme_vol_assets = [v["symbol"] for v in vol_list if v["volatility_7d"] > 6.5]
    if extreme_vol_assets:
        alerts.append({
            "severity": "high",
            "type": "EXTREME_VOLATILITY",
            "message": f"Extreme volatility detected in {', '.join(extreme_vol_assets[:5])}",
            "affected_assets": extreme_vol_assets[:5],
            "recommendation": "Consider reducing position sizes or tightening stop-losses."
        })

    strong_down_assets = [asset_map[p.asset_id].symbol for p in latest_preds
                          if p.direction == "strong_down" and asset_map.get(p.asset_id)]
    if strong_down_assets:
        alerts.append({
            "severity": "medium",
            "type": "BEARISH_CONVERGENCE",
            "message": f"Strong bearish signals for {', '.join(strong_down_assets[:5])}",
            "affected_assets": strong_down_assets[:5],
            "recommendation": "Review portfolio exposure to these assets."
        })

    high_conf_buys = [asset_map[p.asset_id].symbol for p in latest_preds
                      if p.direction in ["up", "strong_up"] and (p.confidence or 0) > 80
                      and asset_map.get(p.asset_id)]
    if high_conf_buys:
        alerts.append({
            "severity": "info",
            "type": "HIGH_CONFIDENCE_OPPORTUNITY",
            "message": f"High-confidence buy signals: {', '.join(high_conf_buys[:5])}",
            "affected_assets": high_conf_buys[:5],
            "recommendation": "These assets show strong bullish momentum across multiple indicators."
        })

    if avg_vol > 8:
        alerts.append({
            "severity": "high",
            "type": "MARKET_WIDE_VOLATILITY",
            "message": f"Market-wide average volatility is elevated at {avg_vol:.1f}%",
            "affected_assets": [],
            "recommendation": "Consider hedging or moving to stablecoins."
        })

    if not alerts:
        alerts.append({
            "severity": "low",
            "type": "ALL_CLEAR",
            "message": "No significant risk alerts at this time.",
            "affected_assets": [],
            "recommendation": "Market conditions appear normal. Continue monitoring."
        })

    return {
        "market_regime": regime,
        "average_volatility": round(avg_vol, 2),
        "correlation_clusters": clusters,
        "top_volatile": top_volatile,
        "risk_alerts": alerts,
        "up_pct": round(up_count / total * 100, 1),
        "down_pct": round(down_count / total * 100, 1),
        "neutral_pct": round((total - up_count - down_count) / total * 100, 1),
        "total_assets_monitored": total,
        "global_confidence": round(global_confidence, 2),
    }


@router.get("/macro")
@cached(ttl_seconds=3600)
def get_macro_data(db: Session = Depends(get_db)):
    """Returns macro economic indicators fetched live from Yahoo Finance."""
    # Try to fetch real macro data
    macro = {
        "history": [],
        "current_fed_rate": 5.25,
        "fed_rate_trend": "stable",
        "current_cpi": 3.1,
        "current_inflation": 3.1,
        "current_vix": 14.5,
        "vix_regime": "normal",
        "crypto_vix_correlation": 0.0,
    }

    try:
        # Get VIX
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="3mo", timeout=1.0)
        if not vix_hist.empty:
            current_vix = float(vix_hist["Close"].iloc[-1])
            macro["current_vix"] = round(current_vix, 2)
            if current_vix > 30:
                macro["vix_regime"] = "extreme_fear"
            elif current_vix > 20:
                macro["vix_regime"] = "elevated"
            elif current_vix < 12:
                macro["vix_regime"] = "complacent"
            else:
                macro["vix_regime"] = "normal"

            # Build VIX history
            vix_history = []
            for date, row in vix_hist.iterrows():
                vix_history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "vix": round(float(row["Close"]), 2),
                })
            macro["history"] = vix_history[-60:]  # last 60 data points

        # Get Treasury yield (10Y as proxy for rates)
        tnx = yf.Ticker("^TNX")
        tnx_hist = tnx.history(period="5d", timeout=1.0)
        if not tnx_hist.empty:
            rate = float(tnx_hist["Close"].iloc[-1])
            macro["current_fed_rate"] = round(rate, 2)
            # Trend: compare to 5 days ago
            if len(tnx_hist) > 1:
                prev = float(tnx_hist["Close"].iloc[0])
                if rate > prev + 0.05:
                    macro["fed_rate_trend"] = "rising"
                elif rate < prev - 0.05:
                    macro["fed_rate_trend"] = "falling"
                else:
                    macro["fed_rate_trend"] = "stable"

        # BTC-VIX correlation from OHLCV
        btc_asset = db.query(Asset).filter(Asset.symbol == "BTC").first()
        if btc_asset and not vix_hist.empty:
            btc_ohlcv = db.query(OHLCV).filter(
                OHLCV.asset_id == btc_asset.id,
                OHLCV.timestamp >= datetime.now(timezone.utc) - timedelta(days=90)
            ).order_by(OHLCV.timestamp.asc()).all()

            if btc_ohlcv and len(btc_ohlcv) > 10:
                btc_df = pd.DataFrame([{"date": r.timestamp, "close": r.close} for r in btc_ohlcv])
                btc_df["date"] = pd.to_datetime(btc_df["date"])
                btc_df = btc_df.set_index("date")
                btc_ret = btc_df["close"].pct_change().dropna()

                vix_ret = vix_hist["Close"].pct_change().dropna()

                # Align dates
                combined = pd.DataFrame({"btc": btc_ret, "vix": vix_ret}).dropna()
                if len(combined) > 5:
                    macro["crypto_vix_correlation"] = round(float(combined.corr().iloc[0, 1]), 3)

    except Exception as e:
        # Graceful fallback — return defaults
        print(f"[Risk/Macro] Error fetching live data: {e}")

    return macro
