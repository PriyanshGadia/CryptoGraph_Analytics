import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
from pathlib import Path

from app.core.streams.binance_ws import get_latest_features, LIVE_OHLCV_CACHE, get_global_market_state

router = APIRouter(prefix="/stream", tags=["stream"])

prediction_refresh_event: asyncio.Event = None

def get_refresh_event() -> asyncio.Event:
    global prediction_refresh_event
    if prediction_refresh_event is None:
        prediction_refresh_event = asyncio.Event()
    return prediction_refresh_event

# Discover SYMBOLS from local database dynamically
def get_db_symbols() -> List[str]:
    try:
        from app.db.database import SessionLocal
        from app.db.models_sqla import Asset
        db = SessionLocal()
        try:
            assets = db.query(Asset.symbol).all()
            if assets:
                return [a.symbol for a in assets]
        finally:
            db.close()
    except Exception as e:
        print(f"Error querying symbols from database: {e}")
        
    # Hardcoded fallback of all 50 database assets
    return [
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
        "MATIC", "UNI", "ATOM", "LTC", "BCH", "NEAR", "APT", "ICP", "STX", "FIL",
        "AR", "HBAR", "VET", "MKR", "INJ", "GRT", "OP", "THETA",
        "LDO", "FET", "FTM", "TAO", "TIA", "SEI", "SUI", "PYTH", "JUP", "GALA",
        "AAVE", "ALGO", "SAND", "EGLD", "QNT", "SNX", "AXS", "CHZ", "MANA", "MINA",
        "DYDX"
    ]

SYMBOLS = get_db_symbols()


@router.post("/broadcast")
async def trigger_broadcast():
    get_refresh_event().set()
    return {"status": "triggered"}

@router.websocket("/ticker/{symbol}")
async def stream_ticker(websocket: WebSocket, symbol: str):
    await websocket.accept()
    sym = symbol.upper()
    try:
        last_price = None
        while True:
            state = get_global_market_state().get(sym)
            if state:
                curr_price = state.get("current_price")
                if last_price != curr_price:
                    last_price = curr_price
                    # We broadcast the full SSOT for consistency
                    await websocket.send_json({
                        "time": int(time.time()),
                        "close": curr_price,
                        "open": curr_price, # Send same for simplicity, frontend mostly uses close for live updates
                        "high": curr_price,
                        "low": curr_price,
                        "volume": state.get("volume_24h", 0),
                        "market_cap_usd": state.get("market_cap_usd", 0),
                        "price_change_24h_pct": state.get("price_change_24h_pct", 0)
                    })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass

@router.websocket("/market")
async def stream_market(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            state = get_global_market_state()
            payload = {}
            for sym, data in state.items():
                payload[sym] = {
                    "time": int(time.time()),
                    "close": data.get("current_price", 0),
                    "volume": data.get("volume_24h", 0),
                    "market_cap_usd": data.get("market_cap_usd", 0),
                    "price_change_24h_pct": data.get("price_change_24h_pct", 0)
                }
            if payload:
                await websocket.send_json({"type": "MARKET_UPDATE", "data": payload})
            await asyncio.sleep(1.0) # Send market updates once per second
    except WebSocketDisconnect:
        pass

connected_clients: List[WebSocket] = []
MAX_CLIENTS = 100

@router.websocket("/predictions")
async def stream_predictions(websocket: WebSocket):
    if len(connected_clients) >= MAX_CLIENTS:
        await websocket.accept()
        await websocket.send_json({"error": "Server busy. Too many active connections."})
        await websocket.close(code=1008) # Policy Violation
        return

    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

async def prediction_broadcast_loop():
    """Background task to broadcast predictions directly from SQLite database."""
    
    while True:
        try:
            # Wait for event to be set, or timeout every 60 seconds
            await asyncio.wait_for(get_refresh_event().wait(), timeout=60.0)
            get_refresh_event().clear()
        except asyncio.TimeoutError:
            pass # Timeout reached, proceed with broadcast

        
        if not connected_clients:
            continue
            
        try:
            from app.db.database import SessionLocal
            from app.db.models_sqla import Prediction as SQLAPrediction, Asset
            from sqlalchemy import desc
            
            db = SessionLocal()
            res = db.query(SQLAPrediction, Asset).join(Asset).order_by(desc(SQLAPrediction.predicted_at)).all()
            
            latest_preds = {}
            for pred, asset in res:
                if asset.symbol not in latest_preds:
                    latest_preds[asset.symbol] = pred
            
            # Sync SSOT with fresh prediction data while we have an open session
            try:
                from app.core.streams.binance_ws import refresh_predictions_in_ssot
                refresh_predictions_in_ssot(db)
            except Exception:
                pass
            
            db.close()
            
            predictions = []
            for symbol in SYMBOLS:
                pred = latest_preds.get(symbol)
                if pred:
                    predictions.append({
                        "symbol": symbol,
                        "direction": pred.direction or "neutral",
                        "confidence": round(pred.confidence, 2) if pred.confidence else 0.0,
                        "volatility_regime": pred.volatility_regime or "medium",
                        "model_version": pred.model_version or "stgcn-v1.0",
                        "attestation_hash": pred.attestation_hash
                    })
                
            if predictions:
                payload = json.dumps({"type": "LIVE_PREDICTIONS", "data": predictions})
                for client in connected_clients:
                    try:
                        await client.send_text(payload)
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"[Stream] Error broadcasting live predictions: {e}")

screener_clients: List[WebSocket] = []

@router.websocket("/screener")
async def stream_screener(websocket: WebSocket):
    await websocket.accept()
    screener_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        screener_clients.remove(websocket)

async def screener_broadcast_loop():
    """Background task to broadcast SSOT state to screener."""
    while True:
        await asyncio.sleep(1)
        if not screener_clients:
            continue
            
        state = get_global_market_state()
        payload_data = {}
        for symbol, data in state.items():
            payload_data[symbol] = {
                "price": data.get("current_price", 0),
                "volume": data.get("volume_24h", 0),
                "market_cap_usd": data.get("market_cap_usd", 0),
                "time": int(time.time())
            }
                
        if payload_data:
            payload = json.dumps({"type": "LIVE_PRICES", "data": payload_data})
            for client in screener_clients:
                try:
                    await client.send_text(payload)
                except Exception:
                    pass
