import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List

from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.pipelines.inference_pipeline import SYMBOLS, MODEL_PATH, DIRECTION_CLASSES, VOLATILITY_CLASSES
from app.core.streams.binance_ws import get_latest_features, LIVE_OHLCV_CACHE
import torch
import torch.nn.functional as F

router = APIRouter(prefix="/stream", tags=["stream"])

FORCE_PREDICTION_BROADCAST = False

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
        from app.db.database import SessionLocal
        from app.db.models_sqla import Asset
        import time
        
        db = SessionLocal()
        asset = db.query(Asset).filter(Asset.symbol == sym).first()
        db.close()
        
        static_price = asset.current_price if asset else 0.0
        
        # Send initial static price immediately to activate UI 'Live' indicators
        await websocket.send_json({
            "time": int(time.time()),
            "open": static_price,
            "high": static_price,
            "low": static_price,
            "close": static_price,
            "volume": 0
        })
        
        last_ts = None
        last_close = None
        last_volume = None
        while True:
            cache_list = LIVE_OHLCV_CACHE.get(sym)
            if cache_list and len(cache_list) > 0:
                latest = cache_list[-1]
                ts = int(latest["timestamp"].timestamp())
                if last_ts != ts or last_close != latest["close"] or last_volume != latest["volume"]:
                    last_ts = ts
                    last_close = latest["close"]
                    last_volume = latest["volume"]
                    await websocket.send_json({
                        "time": ts,
                        "open": latest["open"],
                        "high": latest["high"],
                        "low": latest["low"],
                        "close": latest["close"],
                        "volume": latest["volume"]
                    })
            await asyncio.sleep(0.1) # Send at most 10 times per second
    except WebSocketDisconnect:
        pass

@router.websocket("/market")
async def stream_market(websocket: WebSocket):
    await websocket.accept()
    try:
        last_price_dict = {}
        while True:
            payload = {}
            has_updates = False
            for sym, cache_list in LIVE_OHLCV_CACHE.items():
                if cache_list and len(cache_list) > 0:
                    latest = cache_list[-1]
                    price = latest["close"]
                    if last_price_dict.get(sym) != price:
                        last_price_dict[sym] = price
                        has_updates = True
                        payload[sym] = {
                            "time": int(latest["timestamp"].timestamp()),
                            "open": latest["open"],
                            "high": latest["high"],
                            "low": latest["low"],
                            "close": latest["close"],
                            "volume": latest["volume"]
                        }
            if has_updates:
                await websocket.send_json({"type": "MARKET_UPDATE", "data": payload})
            await asyncio.sleep(1.0) # Send market updates once per second
    except WebSocketDisconnect:
        pass

# Store connected clients
connected_clients: List[WebSocket] = []

@router.websocket("/predictions")
async def stream_predictions(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            # We can ping the client or just wait for them to disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def prediction_broadcast_loop():
    """Background task to compute and broadcast live predictions."""
    model = None
    model_version = "n/a"
    if MODEL_PATH.exists():
        try:
            model = STGCNModel.load(str(MODEL_PATH))
            model.eval()
            model_version = model.config.get("version", MODEL_PATH.stem)
        except Exception as e:
            print(f"Error loading model for stream: {e}")
            
    # Try to extract feature_dim from model config, default to 24
    feature_dim = model.config.get("in_features", 24) if model else 24
            
    builder = DynamicGraphBuilder(supabase_client=None, asset_symbols=SYMBOLS, feature_dim=feature_dim)
    
    global FORCE_PREDICTION_BROADCAST
    
    while True:
        # Sleep for 60 seconds, but check for manual override every second
        for _ in range(60):
            if FORCE_PREDICTION_BROADCAST:
                FORCE_PREDICTION_BROADCAST = False
                break
            await asyncio.sleep(1.0)
        
        if not connected_clients:
            continue
            
        features = get_latest_features()
        if not features:
            continue
            
        try:
            predictions = []
            for idx, symbol in enumerate(SYMBOLS):
                feat = features.get(symbol, {})
                
                direction = "neutral"
                confidence = 50.0
                vol_regime = "medium"
                
                if feat:
                    rsi = feat.get("rsi_14", 50.0)
                    macd = feat.get("macd", 0.0)
                    macd_sig = feat.get("macd_signal", 0.0)
                    vol = feat.get("volatility_7d", 0.0)
                    
                    score = 0
                    if rsi < 35: score += 2
                    elif rsi < 45: score += 1
                    elif rsi > 65: score -= 2
                    elif rsi > 55: score -= 1
                    
                    if macd > macd_sig: score += 1
                    else: score -= 1
                    
                    if score >= 2:
                        direction = "strong_up"
                        confidence = 80.0 + (score * 5.0)
                    elif score == 1:
                        direction = "up"
                        confidence = 60.0 + (score * 5.0)
                    elif score <= -2:
                        direction = "strong_down"
                        confidence = 80.0 + (abs(score) * 5.0)
                    elif score == -1:
                        direction = "down"
                        confidence = 60.0 + (abs(score) * 5.0)
                        
                    confidence = min(99.0, max(50.0, confidence))
                    
                    if vol < 0.025: vol_regime = "low"
                    elif vol > 0.065: vol_regime = "extreme"
                    elif vol > 0.040: vol_regime = "high"
                
                predictions.append({
                    "symbol": symbol,
                    "direction": direction,
                    "confidence": round(confidence, 2),
                    "volatility_regime": vol_regime,
                    "model_version": model_version,
                })
                
            # Broadcast to all connected clients
            payload = json.dumps({"type": "LIVE_PREDICTIONS", "data": predictions})
            for client in connected_clients:
                try:
                    await client.send_text(payload)
                except:
                    # Client likely disconnected
                    pass
                    
        except Exception as e:
            print(f"[Stream] Error computing live predictions: {e}")

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
    """Background task to broadcast live prices every second."""
    while True:
        await asyncio.sleep(1)
        if not screener_clients:
            continue
            
        payload_data = {}
        for symbol, cache_list in LIVE_OHLCV_CACHE.items():
            if cache_list:
                latest = cache_list[-1]
                payload_data[symbol] = {
                    "price": latest["close"],
                    "volume": latest["volume"],
                    "time": int(latest["timestamp"].timestamp())
                }
                
        if payload_data:
            payload = json.dumps({"type": "LIVE_PRICES", "data": payload_data})
            for client in screener_clients:
                try:
                    await client.send_text(payload)
                except:
                    pass
