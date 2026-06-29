"""Asset routes for ST-GCN Forecasting API."""
from fastapi import APIRouter
from app.db.models import Asset
from app.core.streams.binance_ws import get_global_market_state

router = APIRouter(prefix="/assets", tags=["assets"])

@router.get("", response_model=list[Asset])
def get_assets():
    """
    Returns all tracked assets with latest price and prediction from SSOT.
    """
    state = get_global_market_state()
    
    results = []
    for sym, data in state.items():
        results.append(Asset(
            id=data.get("id", ""),
            symbol=sym,
            name=data.get("name", sym),
            sector=data.get("sector", "other"),
            market_cap_usd=data.get("market_cap_usd", 0.0),
            current_price=data.get("current_price", 0.0),
            price_change_24h_pct=data.get("price_change_24h_pct", 0.0),
            predicted_direction=data.get("predicted_direction", "neutral"),
            confidence=data.get("confidence", 0.0),
            confidence_interval=data.get("confidence_interval", None)
        ))
        
    # Sort by market cap descending
    results.sort(key=lambda x: x.market_cap_usd or 0.0, reverse=True)
    return results
