"""Asset routes for ST-GCN Forecasting API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db
from app.db.models import Asset
from app.core.streams.binance_ws import LIVE_OHLCV_CACHE

router = APIRouter(prefix="/assets", tags=["assets"])

@router.get("", response_model=list[Asset])
def get_assets(db: Session = Depends(get_db)):
    """
    Returns all tracked assets with latest price and prediction.
    Uses a batched query to fix N+1 problem.
    24h returns are computed from OHLCV data (24th-most-recent vs latest close)
    and augmented by live WebSocket cache for real-time prices.
    """
    query = text("""
        WITH latest_preds AS (
            SELECT asset_id, direction, confidence,
                   ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY predicted_at DESC) as rn
            FROM predictions
        ),
        latest_ohlcv AS (
            SELECT asset_id, close, timestamp,
                   ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY timestamp DESC) as rn
            FROM ohlcv
        ),
        latest_tech AS (
            SELECT asset_id, returns_1d
            FROM technical_features
            WHERE (asset_id, timestamp) IN (
                SELECT asset_id, MAX(timestamp)
                FROM technical_features
                GROUP BY asset_id
            )
        )
        SELECT a.id, a.symbol, a.name, a.sector, a.market_cap_usd,
               o1.close as current_price,
               t.returns_1d,
               p.direction as predicted_direction,
               p.confidence as confidence
        FROM assets a
        LEFT JOIN latest_ohlcv o1 ON a.id = o1.asset_id AND o1.rn = 1
        LEFT JOIN latest_tech t ON a.id = t.asset_id
        LEFT JOIN latest_preds p ON a.id = p.asset_id AND p.rn = 1
    """)
    
    rows = db.execute(query).fetchall()
    
    results = []
    for row in rows:
        current_price = row.current_price
        
        # Prefer live WebSocket price if available
        live_cache = LIVE_OHLCV_CACHE.get(row.symbol)
        if live_cache:
            current_price = live_cache[-1]["close"]
        
        # Use real 24h return from technical_features (returns_1d is a decimal fraction)
        price_change_pct = None
        if row.returns_1d is not None and row.returns_1d != 0:
            price_change_pct = row.returns_1d * 100  # Convert to percentage
            
        results.append(Asset(
            id=row.id,
            symbol=row.symbol,
            name=row.name or row.symbol,
            sector=row.sector or 'other',
            market_cap_usd=row.market_cap_usd,
            current_price=current_price,
            price_change_24h_pct=price_change_pct,
            predicted_direction=row.predicted_direction or "neutral",
            confidence=row.confidence or 0.0
        ))
        
    return results
