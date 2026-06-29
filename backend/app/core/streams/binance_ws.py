import asyncio
import json
import websockets
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models_sqla import Asset, OnchainMetric, AssetNews, TechnicalFeature, Prediction

# In-memory cache for live OHLCV data.
# Structure: { symbol: [ {timestamp, open, high, low, close, volume}, ... ] }
LIVE_OHLCV_CACHE: Dict[str, List[Dict]] = {}
CACHE_MAX_SIZE = 60  # Keep last 60 minutes

# Static features cache (used by get_latest_features for ML)
STATIC_FEATURES_CACHE: Dict[str, Dict] = {}

# SINGLE SOURCE OF TRUTH State
GLOBAL_MARKET_STATE: Dict[str, Dict] = {}

def populate_static_features(db: Session, symbols: List[str]):
    """Populates the static features cache and initializes GLOBAL_MARKET_STATE with DB data."""
    assets = db.query(Asset).filter(Asset.symbol.in_(symbols)).all()
    
    for asset in assets:
        sym = asset.symbol
        static_dict = {}
        
        # 1. Base Features Defaults
        for col in [
            "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
            "returns_1d", "returns_7d", "volatility_7d", 
            "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
            "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
            "fed_rate", "cpi", "inflation", "vix"
        ]:
            static_dict[col] = 0.0

        # Technical Features
        tf = db.query(TechnicalFeature).filter(TechnicalFeature.asset_id == asset.id).order_by(desc(TechnicalFeature.timestamp)).first()
        if tf:
            static_dict["rsi_14"] = tf.rsi_14 or 50.0
            static_dict["macd"] = tf.macd or 0.0
            static_dict["macd_signal"] = tf.macd_signal or 0.0
            static_dict["atr_14"] = tf.atr_14 or 0.0
            static_dict["bb_width"] = tf.bb_width or 0.0
            static_dict["returns_1d"] = tf.returns_1d or 0.0
            static_dict["returns_7d"] = tf.returns_7d or 0.0
            static_dict["volatility_7d"] = tf.volatility_7d or 0.0
                
        # Onchain Features
        oc = db.query(OnchainMetric).filter(OnchainMetric.asset_id == asset.id).order_by(desc(OnchainMetric.timestamp)).first()
        if oc:
            static_dict["tvl"] = oc.tvl or 0.0
            static_dict["revenue"] = oc.revenue or 0.0
            static_dict["active_users"] = oc.active_users or 0.0
            
        static_dict["market_cap_usd"] = asset.market_cap_usd or 0.0
        STATIC_FEATURES_CACHE[sym] = static_dict

        # Prediction
        pred = db.query(Prediction).filter(Prediction.asset_id == asset.id).order_by(desc(Prediction.predicted_at)).first()

        # Initialize SSOT State
        GLOBAL_MARKET_STATE[sym] = {
            "id": asset.id,
            "symbol": sym,
            "name": asset.name or sym,
            "sector": asset.sector or "other",
            "market_cap_usd": asset.market_cap_usd or 0.0,
            "circulating_supply": 0.0, # Will be derived dynamically if needed
            "current_price": 0.0, # Updated by WS
            "volume_24h": 0.0,    # Updated by WS
            "price_change_24h_pct": static_dict["returns_1d"] * 100, # Initial fallback, updated by WS
            "rsi_14": static_dict["rsi_14"],
            "returns_7d": static_dict["returns_7d"],
            "volatility_7d": static_dict["volatility_7d"],
            "predicted_direction": pred.direction if pred else "neutral",
            "confidence": pred.confidence if pred else 0.0,
        }

def get_global_market_state() -> Dict[str, Dict]:
    """Returns the Single Source of Truth market state for all tracked assets."""
    return GLOBAL_MARKET_STATE

async def binance_ws_loop(symbols: List[str]):
    # kline_1m for OHLCV cache (used by ML features)
    kline_streams = [f"{s.lower()}usdt@kline_1m" for s in symbols]
    
    # ticker stream for 24h stats (price, volume, change)
    ticker_streams = [f"{s.lower()}usdt@ticker" for s in symbols]
    
    all_streams = kline_streams + ticker_streams
    ws_url = "wss://stream.binance.com:9443/ws"
    
    for s in symbols:
        if s not in LIVE_OHLCV_CACHE:
            LIVE_OHLCV_CACHE[s] = []

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                # Binance limits to 1024 streams per subscription payload, we have ~100
                subscribe_payload = {
                    "method": "SUBSCRIBE",
                    "params": all_streams,
                    "id": 1
                }
                await ws.send(json.dumps(subscribe_payload))
                print(f"[BinanceWS] Connected to live kline & ticker streams for {len(symbols)} assets.")
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if "e" in data:
                        symbol = data["s"].replace("USDT", "")
                        
                        if data["e"] == "kline":
                            kline = data["k"]
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
                            
                        elif data["e"] == "24hrTicker":
                            # Update SSOT State with real 24h data
                            if symbol in GLOBAL_MARKET_STATE:
                                live_price = float(data["c"])
                                # Dynamic Market Cap Scaling if we have static mcap > 0
                                static_mcap = GLOBAL_MARKET_STATE[symbol].get("market_cap_usd", 0)
                                current_mcap = static_mcap
                                
                                # Optionally derive circulating supply on first tick and use it to scale mcap dynamically
                                if GLOBAL_MARKET_STATE[symbol].get("circulating_supply", 0) == 0 and live_price > 0 and static_mcap > 0:
                                    GLOBAL_MARKET_STATE[symbol]["circulating_supply"] = static_mcap / live_price
                                
                                circ_supply = GLOBAL_MARKET_STATE[symbol].get("circulating_supply", 0)
                                if circ_supply > 0:
                                    current_mcap = circ_supply * live_price
                                
                                GLOBAL_MARKET_STATE[symbol]["current_price"] = live_price
                                GLOBAL_MARKET_STATE[symbol]["volume_24h"] = float(data["q"]) # Quote asset volume (USDT)
                                GLOBAL_MARKET_STATE[symbol]["price_change_24h_pct"] = float(data["P"]) # Price change percent
                                GLOBAL_MARKET_STATE[symbol]["market_cap_usd"] = current_mcap

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
        
        static_data = STATIC_FEATURES_CACHE.get(sym, {})
        for col, val in static_data.items():
            df[col] = val
            
        features[sym] = df
    return features
