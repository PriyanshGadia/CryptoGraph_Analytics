"""Asset routes for ST-GCN Forecasting API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db
from app.db.models import Asset

router = APIRouter(prefix="/assets", tags=["assets"])

@router.get("", response_model=list[Asset])
def get_assets(db: Session = Depends(get_db)):
    """
    Returns all tracked assets with latest price and prediction.
    Uses a batched query to fix N+1 problem.
    """
    query = text("""
        WITH latest_preds AS (
            SELECT asset_id, direction, confidence,
                   ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY predicted_at DESC) as rn
            FROM predictions
        ),
        latest_ohlcv AS (
            SELECT asset_id, close,
                   ROW_NUMBER() OVER(PARTITION BY asset_id ORDER BY timestamp DESC) as rn
            FROM ohlcv
        )
        SELECT a.id, a.symbol, a.name, a.sector, a.market_cap_usd,
               o1.close as current_price,
               o2.close as previous_price,
               p.direction as predicted_direction,
               p.confidence as confidence
        FROM assets a
        LEFT JOIN latest_ohlcv o1 ON a.id = o1.asset_id AND o1.rn = 1
        LEFT JOIN latest_ohlcv o2 ON a.id = o2.asset_id AND o2.rn = 2
        LEFT JOIN latest_preds p ON a.id = p.asset_id AND p.rn = 1
    """)
    
    rows = db.execute(query).fetchall()
    
    results = []
    for row in rows:
        current_price = row.current_price
        previous_price = row.previous_price
        price_change_pct = None
        
        if current_price is not None and previous_price is not None and previous_price > 0:
            price_change_pct = ((current_price - previous_price) / previous_price) * 100
            
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
