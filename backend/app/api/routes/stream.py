import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
from pathlib import Path

from app.core.streams.binance_ws import get_latest_features, LIVE_OHLCV_CACHE, get_global_market_state

router = APIRouter(prefix="/stream", tags=["stream"])

FORCE_PREDICTION_BROADCAST = False

# Discover SYMBOLS
try:
    from ml.pipelines.inference_pipeline import SYMBOLS
except ImportError:
    SYMBOLS = [
        "BTC","ETH","BNB","SOL","XRP","ADA","AVAX","DOT","MATIC","LINK",
        "DOGE","SHIB","UNI","LTC","ATOM","NEAR","FIL","APT","ARB","OP",
        "AAVE","MKR","CRV","SNX","COMP","RUNE","INJ","FTM","MANA","SAND",
        "AXS","GALA","ENJ","LRC","IMX","ALGO","VET","EOS","XLM","XTZ",
        "HBAR","EGLD","THETA","ICP","GRT","STX","FLOW","KAVA","ZEC","DASH"
    ]

@router.post("/broadcast")
async def trigger_broadcast():
    global FORCE_PREDICTION_BROADCAST
    FORCE_PREDICTION_BROADCAST = True
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

@router.websocket("/predictions")
async def stream_predictions(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def prediction_broadcast_loop():
    """Background task to broadcast predictions."""
    model_version = "heuristic-v1"
    
    global FORCE_PREDICTION_BROADCAST
    
    while True:
        for _ in range(60):
            if FORCE_PREDICTION_BROADCAST:
                FORCE_PREDICTION_BROADCAST = False
                break
            await asyncio.sleep(1.0)
        
        if not connected_clients:
            continue
            
        state = get_global_market_state()
        if not state:
            continue
            
        try:
            predictions = []
            for symbol, data in state.items():
                predictions.append({
                    "symbol": symbol,
                    "direction": data.get("predicted_direction", "neutral"),
                    "confidence": data.get("confidence", 50.0),
                    "volatility_regime": data.get("volatility_regime", "low"),
                    "model_version": model_version,
                })
                
            payload = json.dumps({"type": "LIVE_PREDICTIONS", "data": predictions})
            for client in connected_clients:
                try:
                    await client.send_text(payload)
                except:
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
                except:
                    pass
