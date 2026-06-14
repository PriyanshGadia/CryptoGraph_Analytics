import asyncio
import json
import websockets
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models_sqla import Asset, OnchainMetric, AssetNews

# In-memory cache for live OHLCV data.
# Structure: { symbol: [ {timestamp, open, high, low, close, volume}, ... ] }
LIVE_OHLCV_CACHE: Dict[str, List[Dict]] = {}
CACHE_MAX_SIZE = 60  # Keep last 60 minutes

# Static features cache (fetched once or periodically from DB)
STATIC_FEATURES_CACHE: Dict[str, Dict] = {}

def populate_static_features(db: Session, symbols: List[str]):
    """Populates the static features cache with the latest available data."""
    assets = db.query(Asset).filter(Asset.symbol.in_(symbols)).all()
    asset_map = {a.id: a.symbol for a in assets}
    
    for asset in assets:
        static_dict = {}
        
        # 1. Base Features
        # Provide zero defaults for required columns
        for col in [
            "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d", 
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
            "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi", "inflation", "vix"
        ]:
            static_dict[col] = 0.0

                
        # 2. Onchain Features
        oc = db.query(OnchainMetric).filter(OnchainMetric.asset_id == asset.id).order_by(desc(OnchainMetric.timestamp)).first()
        if oc:
            static_dict["tvl"] = oc.tvl or 0.0
            static_dict["revenue"] = oc.revenue or 0.0
            static_dict["active_users"] = oc.active_users or 0.0
        else:
            static_dict["tvl"] = 0.0
            static_dict["revenue"] = 0.0
            static_dict["active_users"] = 0.0
            
        STATIC_FEATURES_CACHE[asset.symbol] = static_dict

async def binance_ws_loop(symbols: List[str]):
    # Binance streams are lowercase symbol + @kline_1m
    stream_names = [f"{s.lower()}usdt@kline_1m" for s in symbols]
    
    # Binance limits stream combinations to 1024 streams per connection
    # We only have ~50 symbols, so 1 connection is fine.
    # However, if we subscribe to too many at once in the URL, it might be too long.
    # Binance supports subscribing via payload. Let's do that for safety.
    
    ws_url = "wss://stream.binance.com:9443/ws"
    
    for s in symbols:
        if s not in LIVE_OHLCV_CACHE:
            LIVE_OHLCV_CACHE[s] = []

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                # Send subscription payload
                subscribe_payload = {
                    "method": "SUBSCRIBE",
                    "params": stream_names,
                    "id": 1
                }
                await ws.send(json.dumps(subscribe_payload))
                print(f"[BinanceWS] Connected to live streams for {len(symbols)} assets.")
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if "e" in data and data["e"] == "kline":
                        kline = data["k"]
                        symbol = data["s"].replace("USDT", "")
                        
                        kline_start = kline["t"]
                        timestamp = pd.to_datetime(kline_start, unit='ms', utc=True)
                        
                        ohlcv = {
                            "timestamp": timestamp,
                            "open": float(kline["o"]),
                            "high": float(kline["h"]),
                            "low": float(kline["l"]),
                            "close": float(kline["c"]),
                            "volume": float(kline["v"])
                        }
                        
                        cache_list = LIVE_OHLCV_CACHE.get(symbol, [])
                        
                        if len(cache_list) > 0 and cache_list[-1]["timestamp"] == timestamp:
                            cache_list[-1] = ohlcv
                        else:
                            cache_list.append(ohlcv)
                            if len(cache_list) > CACHE_MAX_SIZE:
                                cache_list.pop(0)
                        
                        LIVE_OHLCV_CACHE[symbol] = cache_list
                        
        except Exception as e:
            print(f"[BinanceWS] Connection error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

def get_latest_features() -> Dict[str, pd.DataFrame]:
    """Returns the latest 60-min window as pandas DataFrames per symbol, merged with static features."""
    features = {}
    for sym, cache_list in LIVE_OHLCV_CACHE.items():
        if not cache_list:
            continue
            
        df = pd.DataFrame(cache_list)
        df.set_index("timestamp", inplace=True)
        
        # Merge with static features
        static_data = STATIC_FEATURES_CACHE.get(sym, {})
        for col, val in static_data.items():
            df[col] = val
            
        features[sym] = df
    return features
