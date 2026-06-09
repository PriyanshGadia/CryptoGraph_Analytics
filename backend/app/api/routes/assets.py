"""Asset routes for ST-GCN Forecasting API."""
from fastapi import APIRouter, Depends
from app.api.deps import get_supabase
from app.db.models import Asset

router = APIRouter(prefix="/assets", tags=["assets"])

@router.get("", response_model=list[Asset])
async def get_assets(db=Depends(get_supabase)):
    """
    Returns all tracked assets with latest price and prediction.

    Query:
    1. Get all rows from assets table
    2. For each asset: get latest ohlcv row (highest timestamp)
       Compute price_change_24h_pct = (close_today - close_yesterday) / close_yesterday * 100
    3. For each asset: get latest predictions row
    4. Return merged list
    """
    # 1. Get assets
    assets_res = db.table("assets").select("*").execute()
    assets_list = assets_res.data
    
    # We will assemble them into the Pydantic models
    results = []
    for ast in assets_list:
        asset_id = ast['id']
        symbol = ast['symbol']
        
        # 2. Get latest OHLCV
        ohlcv_res = db.table("ohlcv").select("*").eq("asset_id", asset_id).order("timestamp", desc=True).limit(2).execute()
        
        current_price = None
        price_change_pct = None
        if ohlcv_res.data and len(ohlcv_res.data) > 0:
            current_price = ohlcv_res.data[0].get('close')
            if len(ohlcv_res.data) == 2:
                close_today = ohlcv_res.data[0].get('close', 0)
                close_yesterday = ohlcv_res.data[1].get('close', 0)
                if close_yesterday and close_yesterday > 0:
                    price_change_pct = ((close_today - close_yesterday) / close_yesterday) * 100

        # 3. Get latest Prediction
        pred_res = db.table("predictions").select("*").eq("asset_id", asset_id).order("predicted_at", desc=True).limit(1).execute()
        
        predicted_direction = "neutral"
        confidence = 0.0
        if pred_res.data and len(pred_res.data) > 0:
            predicted_direction = pred_res.data[0].get('direction')
            confidence = pred_res.data[0].get('confidence')
            
        results.append(Asset(
            id=asset_id,
            symbol=symbol,
            name=ast.get('name', symbol),
            sector=ast.get('sector', 'other'),
            market_cap_usd=None, # Market cap not strictly stored in simple ohlcv, could be pulled if added
            current_price=current_price,
            price_change_24h_pct=price_change_pct,
            predicted_direction=predicted_direction,
            confidence=confidence
        ))
        
    return results
