"""Sentiment data routes — local SQLAlchemy backend.

Uses OHLCV price data + technical_features + asset_news as sentiment proxies
since there is no dedicated sentiment/fear_greed table in the local DB.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from datetime import datetime, timezone, timedelta
from app.api.deps import get_db
from app.db.models import Asset, OHLCV
from app.core.cache import cached
import math

router = APIRouter(prefix="/sentiment-data", tags=["sentiment"])


def _compute_fear_greed(returns_1d: float, volatility_7d: float, rsi_14: float,
                        returns_7d: float = 0.0) -> int:
    """
    Computes a synthetic Fear & Greed index (0-100) from local technical data.

    Components (calibrated to typical crypto ranges):
    - RSI (30% weight): Direct momentum gauge. RSI<30 = extreme fear, RSI>70 = extreme greed.
    - Momentum (25% weight): 7-day returns mapped through a sigmoid to avoid saturation.
    - Short-term returns (20% weight): 24h returns for recency signal.
    - Inverse volatility (15% weight): High vol = fear, low vol = complacency.
    - RSI rate-of-change proxy (10% weight): Acceleration signal from RSI deviation from 50.
    """
    # 1. RSI component: already 0-100, map directly
    rsi_score = max(0, min(100, rsi_14 or 50))

    # 2. 7-day momentum: Use sigmoid to prevent saturation at ±5%
    # sigmoid(x * 8) maps [-0.15, +0.15] smoothly to [0, 100]
    ret7d_val = returns_7d or 0.0
    momentum_raw = 1.0 / (1.0 + math.exp(-ret7d_val * 8))  # 0 to 1
    momentum_score = momentum_raw * 100

    # 3. Short-term returns: 24h using tanh to prevent clipping
    ret1d_val = returns_1d or 0.0
    short_term_raw = math.tanh(ret1d_val * 5)  # -1 to 1
    short_term_score = (short_term_raw + 1) * 50  # 0 to 100

    # 4. Inverse volatility: Map [0%, 8%+] inversely to [0, 100]
    # Lower vol = more greed/complacency, higher vol = more fear
    vol_val = volatility_7d or 0.0
    vol_score = max(0, min(100, 100 - vol_val * 1250))  # 0.08 -> 0, 0.0 -> 100

    # 5. RSI rate of change proxy: how far RSI is from neutral (50)
    # Positive divergence from 50 = greed, negative = fear
    rsi_deviation = ((rsi_14 or 50) - 50) / 50  # -1 to +1
    rsi_roc_score = (rsi_deviation + 1) * 50  # 0 to 100

    # Weighted average with calibrated weights
    fg = int(
        rsi_score * 0.30 +
        momentum_score * 0.25 +
        short_term_score * 0.20 +
        vol_score * 0.15 +
        rsi_roc_score * 0.10
    )
    return max(0, min(100, fg))


def _fg_label(fg: int) -> str:
    """Returns human-readable Fear & Greed label."""
    if fg <= 24:
        return "Extreme Fear"
    elif fg <= 44:
        return "Fear"
    elif fg <= 55:
        return "Neutral"
    elif fg <= 74:
        return "Greed"
    else:
        return "Extreme Greed"


@router.get("/fear-greed-history")
@cached(ttl_seconds=300)
def get_fear_greed_history(days: int = 365, db: Session = Depends(get_db)):
    """Returns fear & greed history from alternative.me, falling back to synthetic if needed."""
    import requests
    try:
        resp = requests.get(f"https://api.alternative.me/fng/?limit={days}", timeout=5)
        if resp.status_code == 200:
            resp_data = resp.json()
            if "data" in resp_data:
                results = []
                for item in resp_data["data"]:
                    val = int(item["value"])
                    ts = int(item["timestamp"])
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    results.append({"date": date_str, "fear_greed": val, "label": item["value_classification"]})
                results.reverse() # API returns newest first
                return results
    except Exception as e:
        import logging
        logging.getLogger("cryptograph.sentiment").warning(f"Alternative.me API failed, using synthetic fallback: {e}")

    # Find BTC
    btc = db.query(Asset).filter(Asset.symbol == "BTC").first()
    if not btc:
        return []

    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.execute(text("""
        SELECT timestamp, returns_1d, volatility_7d, rsi_14, returns_7d
        FROM technical_features
        WHERE asset_id = :aid AND timestamp >= :since
        ORDER BY timestamp ASC
    """), {"aid": btc.id, "since": since.isoformat()}).fetchall()

    data = []
    for r in rows:
        ret_7d = r[4] if len(r) > 4 else 0.0
        fg = _compute_fear_greed(r[1], r[2], r[3], ret_7d)
        label = _fg_label(fg)
        ts = str(r[0])
        date_str = ts.split("T")[0] if "T" in ts else ts[:10]
        data.append({"date": date_str, "fear_greed": fg, "label": label})

    return data


@router.get("/fear-greed-vs-btc")
@cached(ttl_seconds=300)
def get_fear_greed_vs_btc(days: int = 365, db: Session = Depends(get_db)):
    """Returns fear/greed vs BTC close price for dual-axis chart."""
    btc = db.query(Asset).filter(Asset.symbol == "BTC").first()
    if not btc:
        return []

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get OHLCV close prices
    ohlcv_rows = db.query(OHLCV).filter(
        OHLCV.asset_id == btc.id,
        OHLCV.timestamp >= since,
    ).order_by(OHLCV.timestamp.asc()).all()

    # Get technical features for F&G
    tech_rows = db.execute(text("""
        SELECT timestamp, returns_1d, volatility_7d, rsi_14, returns_7d
        FROM technical_features
        WHERE asset_id = :aid AND timestamp >= :since
        ORDER BY timestamp ASC
    """), {"aid": btc.id, "since": since.isoformat()}).fetchall()

    tech_map = {}
    for r in tech_rows:
        ts = str(r[0])
        date_str = ts.split("T")[0] if "T" in ts else ts[:10]
        ret_7d = r[4] if len(r) > 4 else 0.0
        tech_map[date_str] = (r[1], r[2], r[3], ret_7d)

    data = []
    prev_close = None
    for row in ohlcv_rows:
        ts = row.timestamp
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        close = row.close or 0

        tech = tech_map.get(date_str)
        if tech:
            fg = _compute_fear_greed(tech[0], tech[1], tech[2], tech[3])
        else:
            fg = 50  # default neutral

        ret = ((close - prev_close) / prev_close) if prev_close and prev_close > 0 else 0.0
        prev_close = close

        data.append({
            "date": date_str,
            "fear_greed": fg,
            "btc_price": close,
            "btc_return_1d": ret,
        })

    return data


@router.get("/latest-synthesis")
def get_latest_synthesis(db: Session = Depends(get_db)):
    """Returns the most recent qualitative synthesis from the MoA Swarm."""
    from app.db.models import TradeDebate
    latest_debate = db.query(TradeDebate).order_by(desc(TradeDebate.timestamp)).first()
    
    if not latest_debate:
        return {
            "macro_analysis": "No macro analysis available yet.",
            "onchain_analysis": "No on-chain analysis available yet.",
            "sentiment_analysis": "No sentiment analysis available yet.",
            "symbol": "N/A"
        }
        
    return {
        "macro_analysis": latest_debate.macro_analysis,
        "onchain_analysis": latest_debate.onchain_analysis,
        "sentiment_analysis": latest_debate.sentiment_analysis,
        "symbol": latest_debate.symbol
    }


@router.get("/sector-sentiment")
@cached(ttl_seconds=300)
def get_sector_sentiment(db: Session = Depends(get_db)):
    """
    Returns average sentiment by sector using multi-signal approach:
    - Momentum signal: 7-day returns (Z-score normalized within the asset universe)
    - Technical signal: RSI divergence from neutral (50)
    - News activity: Recent news count as public interest proxy
    """
    assets = db.query(Asset).all()
    if not assets:
        return []

    # Get latest technicals per asset (batched)
    tech_rows = db.execute(text("""
        SELECT t1.asset_id, t1.returns_1d, t1.returns_7d, t1.volatility_7d, t1.rsi_14
        FROM technical_features t1
        JOIN (
            SELECT asset_id, MAX(timestamp) as max_ts
            FROM technical_features
            GROUP BY asset_id
        ) t2 ON t1.asset_id = t2.asset_id AND t1.timestamp = t2.max_ts
    """)).fetchall()

    tech_map = {r[0]: {
        "ret1d": r[1] or 0, "ret7d": r[2] or 0,
        "vol7d": r[3] or 0, "rsi": r[4] or 50
    } for r in tech_rows}

    # Compute universe-wide statistics for Z-score normalization
    all_ret7d = [t["ret7d"] for t in tech_map.values() if t["ret7d"] != 0]
    mean_ret7d = sum(all_ret7d) / len(all_ret7d) if all_ret7d else 0.0
    std_ret7d = (sum((x - mean_ret7d) ** 2 for x in all_ret7d) / max(len(all_ret7d), 1)) ** 0.5
    if std_ret7d < 0.001:
        std_ret7d = 0.01  # prevent division by zero

    # Count news per asset as public interest proxy
    news_counts = db.execute(text("""
        SELECT asset_id, COUNT(*) as cnt
        FROM asset_news
        WHERE created_at >= :since
        GROUP BY asset_id
    """), {"since": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}).fetchall()
    news_map = {r[0]: r[1] for r in news_counts}

    sector_aggs = {}
    for a in assets:
        sector = a.sector or "other"
        t = tech_map.get(a.id, {"ret1d": 0, "ret7d": 0, "vol7d": 0, "rsi": 50})
        news_count = news_map.get(a.id, 0)

        # Momentum sentiment: Z-score of 7d returns, then tanh to bound [-1, 1]
        z_score = (t["ret7d"] - mean_ret7d) / std_ret7d
        sent = math.tanh(z_score * 0.5)  # smooth mapping to [-1, 1]

        # Community/technical score: RSI distance from 50, normalized
        # RSI > 50 = positive community momentum, RSI < 50 = negative
        rsi_norm = (t["rsi"] - 50) / 50  # -1 to +1
        comm = max(0, min(1, 0.5 + rsi_norm * 0.5))  # 0 to 1

        pub_interest = min(10, news_count)

        if sector not in sector_aggs:
            sector_aggs[sector] = {"sent_sum": 0, "comm_sum": 0, "pub_sum": 0, "count": 0}

        sector_aggs[sector]["sent_sum"] += sent
        sector_aggs[sector]["comm_sum"] += comm
        sector_aggs[sector]["pub_sum"] += pub_interest
        sector_aggs[sector]["count"] += 1

    results = []
    for sector, aggs in sector_aggs.items():
        count = aggs["count"]
        if count > 0:
            results.append({
                "sector": sector,
                "avg_sentiment": round(aggs["sent_sum"] / count, 4),
                "avg_community": round(aggs["comm_sum"] / count, 4),
                "avg_public_interest": round(aggs["pub_sum"] / count, 2),
                "asset_count": count,
            })

    results.sort(key=lambda x: x["avg_sentiment"], reverse=True)
    return results


@router.get("/trending")
@cached(ttl_seconds=300)
def get_trending_assets(db: Session = Depends(get_db)):
    """
    Returns assets with biggest sentiment momentum changes.
    Compares current technical sentiment score to a 7-day rolling baseline.
    """
    assets = db.query(Asset).all()
    if not assets:
        return {"gainers": [], "losers": []}

    asset_map = {a.id: a for a in assets}

    # Get latest technicals
    tech_rows = db.execute(text("""
        SELECT t1.asset_id, t1.returns_1d, t1.returns_7d, t1.rsi_14, t1.timestamp
        FROM technical_features t1
        JOIN (
            SELECT asset_id, MAX(timestamp) as max_ts
            FROM technical_features
            GROUP BY asset_id
        ) t2 ON t1.asset_id = t2.asset_id AND t1.timestamp = t2.max_ts
    """)).fetchall()

    changes = []
    for r in tech_rows:
        aid = r[0]
        asset = asset_map.get(aid)
        if not asset:
            continue

        ret_1d = r[1] or 0
        ret_7d = r[2] or 0
        rsi = r[3] or 50

        # Current composite sentiment score [-1, 1]:
        # Combine RSI position + 7d returns + 1d returns
        rsi_component = (rsi - 50) / 50  # -1 to +1
        momentum_component = math.tanh(ret_7d * 8)  # sigmoid-like, bounded
        short_component = math.tanh(ret_1d * 12)  # more responsive

        current_sentiment = round(
            rsi_component * 0.4 + momentum_component * 0.4 + short_component * 0.2,
            4
        )

        # Previous sentiment estimate using actual historical data
        prev_row = db.execute(text("""
            SELECT rsi_14, returns_7d FROM technical_features
            WHERE asset_id = :aid AND timestamp < :ts
            ORDER BY timestamp DESC LIMIT 1
        """), {"aid": aid, "ts": r[4]}).fetchone()
        
        prev_rsi = prev_row[0] if prev_row else rsi
        prev_ret_7d = prev_row[1] if prev_row else ret_7d
        
        prev_rsi = max(0, min(100, prev_rsi))
        prev_rsi_component = (prev_rsi - 50) / 50
        prev_momentum = math.tanh(prev_ret_7d * 8)

        prev_sentiment = round(
            prev_rsi_component * 0.5 + prev_momentum * 0.5,
            4
        )

        change = round(current_sentiment - prev_sentiment, 4)

        changes.append({
            "symbol": asset.symbol,
            "sector": asset.sector or "other",
            "current_sentiment": current_sentiment,
            "prev_sentiment": prev_sentiment,
            "change": change,
        })

    changes.sort(key=lambda x: x["change"], reverse=True)
    gainers = changes[:5]
    losers = changes[-5:]
    losers.sort(key=lambda x: x["change"])

    return {"gainers": gainers, "losers": losers}
