import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from typing import List

from app.core.streams.binance_ws import get_global_market_state
from app.api.deps import verify_ws_api_key
from app.api.routes.forecast import limiter
from app.core.state import ws_manager

router = APIRouter(prefix="/stream", tags=["stream"])

def get_refresh_event() -> asyncio.Event:
    return ws_manager.prediction_refresh_event

# Discover SYMBOLS from local database dynamically
def get_db_symbols() -> List[str]:
    try:
        from app.db.database import SessionLocal
        from app.db.models import Asset
        db = SessionLocal()
        try:
            assets = db.query(Asset.symbol).all()
            if assets:
                return [a.symbol for a in assets]
        finally:
            db.close()
    except Exception:
        import logging
        logging.getLogger(__name__).error("Error querying symbols from database", exc_info=True)
        
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
@limiter.limit("5/minute")
async def trigger_broadcast(request: Request):
    get_refresh_event().set()
    return {"status": "triggered"}

@router.websocket("/ticker/{symbol}")
async def stream_ticker(websocket: WebSocket, symbol: str):
    if not await verify_ws_api_key(websocket):
        await websocket.close(code=1008)
        return
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
    if not await verify_ws_api_key(websocket):
        await websocket.close(code=1008)
        return
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

MAX_CLIENTS = 100

@router.websocket("/predictions")
async def stream_predictions(websocket: WebSocket):
    if not await verify_ws_api_key(websocket):
        await websocket.close(code=1008)
        return
        
    async with ws_manager.predictions_lock:
        if len(ws_manager.predictions_clients) >= MAX_CLIENTS:
            await websocket.accept()
            await websocket.send_json({"error": "Server busy. Too many active connections."})
            await websocket.close(code=1008) # Policy Violation
            return
        await websocket.accept()
        ws_manager.predictions_clients.append(websocket)
        
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        async with ws_manager.predictions_lock:
            if websocket in ws_manager.predictions_clients:
                ws_manager.predictions_clients.remove(websocket)

async def prediction_broadcast_loop():
    """Background task to broadcast predictions directly from SQLite database."""
    
    while True:
        try:
            # Wait for event to be set, or timeout every 60 seconds
            await asyncio.wait_for(get_refresh_event().wait(), timeout=60.0)
            get_refresh_event().clear()
        except asyncio.TimeoutError:
            pass # Timeout reached, proceed with broadcast

        async with ws_manager.predictions_lock:
            if not ws_manager.predictions_clients:
                continue
            active_clients = ws_manager.predictions_clients.copy()
            
        try:
            from app.db.database import SessionLocal
            from app.db.models import Prediction as SQLAPrediction, Asset
            from sqlalchemy import desc
            import json
            
            db = SessionLocal()
            try:
                res = db.query(SQLAPrediction, Asset).join(Asset).order_by(desc(SQLAPrediction.predicted_at)).limit(100).all()
                latest_preds = {}
                for pred, asset in res:
                    if asset.symbol not in latest_preds:
                        latest_preds[asset.symbol] = pred
                
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
                    async def send_to_client(ws):
                        try:
                            await ws.send_text(payload)
                        except Exception:
                            async with ws_manager.predictions_lock:
                                if ws in ws_manager.predictions_clients:
                                    ws_manager.predictions_clients.remove(ws)
                    await asyncio.gather(*(send_to_client(ws) for ws in active_clients))
            finally:
                db.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[Stream] Error broadcasting live predictions: {e}", exc_info=True)


@router.websocket("/screener")
async def stream_screener(websocket: WebSocket):
    if not await verify_ws_api_key(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    async with ws_manager.screener_lock:
        ws_manager.screener_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        async with ws_manager.screener_lock:
            if websocket in ws_manager.screener_clients:
                ws_manager.screener_clients.remove(websocket)

async def screener_broadcast_loop():
    """Background task to broadcast SSOT state to screener."""
    while True:
        await asyncio.sleep(1)
        async with ws_manager.screener_lock:
            if not ws_manager.screener_clients:
                continue
            active_screener_clients = ws_manager.screener_clients.copy()
            
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
            for client in active_screener_clients:
                try:
                    await client.send_text(payload)
                except Exception:
                    async with ws_manager.screener_lock:
                        if client in ws_manager.screener_clients:
                            ws_manager.screener_clients.remove(client)
