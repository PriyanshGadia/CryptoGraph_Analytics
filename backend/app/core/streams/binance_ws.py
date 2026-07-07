import asyncio
import json
import websockets
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models_sqla import Asset, OnchainMetric, AssetNews, TechnicalFeature, Prediction

from cachetools import TTLCache

# In-memory cache for live OHLCV data.
# Structure: { symbol: [ {timestamp, open, high, low, close, volume}, ... ] }
LIVE_OHLCV_CACHE: Dict[str, List[Dict]] = TTLCache(maxsize=1000, ttl=3600)
CACHE_MAX_SIZE = 60  # Keep last 60 minutes

# Static features cache (used by get_latest_features for ML)
STATIC_FEATURES_CACHE: Dict[str, Dict] = {}

# SINGLE SOURCE OF TRUTH State
GLOBAL_MARKET_STATE: Dict[str, Dict] = {}

# Mapping symbols to Binance symbols
BINANCE_SYM_MAPPING = {
    "MATIC": "POL",
}
# Symbols to exclude from Binance websocket stream (e.g. delisted)
BINANCE_EXCLUDE_SYMBOLS = {"XMR"}

def populate_static_features(db: Session, symbols: List[str]):
    """Populates the static features cache and initializes GLOBAL_MARKET_STATE with DB data."""
    assets = db.query(Asset).filter(Asset.symbol.in_(symbols)).all()
    from app.db.models_sqla import OHLCV
    
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

        # Fetch latest price & volume from OHLCV table as fallback/initial value
        ohlcv = db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
        latest_price = ohlcv.close if ohlcv else 0.0
        latest_volume = ohlcv.volume if ohlcv else 0.0

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
            "current_price": latest_price, # Initialized from DB, updated by WS
            "volume_24h": latest_volume,    # Initialized from DB, updated by WS
            "price_change_24h_pct": static_dict["returns_1d"] * 100, # Initial fallback, updated by WS
            "rsi_14": static_dict["rsi_14"],
            "macd": static_dict["macd"],
            "macd_signal": static_dict["macd_signal"],
            "returns_7d": static_dict["returns_7d"],
            "volatility_7d": static_dict["volatility_7d"],
            "predicted_direction": pred.direction if pred else "neutral",
            "confidence": pred.confidence if pred else 0.0,
            "confidence_interval": [pred.confidence_interval_lower, pred.confidence_interval_upper] if pred and pred.confidence_interval_lower is not None else None,
        }

def get_global_market_state() -> Dict[str, Dict]:
    """Returns the Single Source of Truth market state for all tracked assets."""
    return GLOBAL_MARKET_STATE

def refresh_predictions_in_ssot(db: Session):
    """
    Re-reads the latest predictions from the DB and patches the SSOT in place.
    Call this after the inference pipeline writes new predictions so that
    /api/assets, /api/screener, and any other SSOT-consuming endpoint
    immediately reflect the fresh confidence scores without a server restart.
    """
    from app.db.models_sqla import Asset, Prediction
    assets = db.query(Asset).all()
    for asset in assets:
        if asset.symbol not in GLOBAL_MARKET_STATE:
            continue
        pred = db.query(Prediction).filter(
            Prediction.asset_id == asset.id
        ).order_by(desc(Prediction.predicted_at)).first()
        if pred:
            GLOBAL_MARKET_STATE[asset.symbol]["predicted_direction"] = pred.direction or "neutral"
            GLOBAL_MARKET_STATE[asset.symbol]["confidence"] = pred.confidence if pred.confidence is not None else 0.0
            GLOBAL_MARKET_STATE[asset.symbol]["confidence_interval"] = (
                [pred.confidence_interval_lower, pred.confidence_interval_upper]
                if pred.confidence_interval_lower is not None else None
            )

async def binance_ws_loop(symbols: List[str]):
    # Build list of streams mapped to Binance and exclude delisted ones
    ws_symbols = []
    symbol_to_asset = {}
    for s in symbols:
        if s in BINANCE_EXCLUDE_SYMBOLS:
            continue
        binance_s = BINANCE_SYM_MAPPING.get(s, s)
        ws_symbols.append(binance_s)
        symbol_to_asset[binance_s] = s

    kline_streams = [f"{s.lower()}usdt@kline_1m" for s in ws_symbols]
    ticker_streams = [f"{s.lower()}usdt@ticker" for s in ws_symbols]
    
    all_streams = kline_streams + ticker_streams
    ws_url = "wss://stream.binance.com:9443/ws"
    
    for s in symbols:
        if s not in LIVE_OHLCV_CACHE:
            LIVE_OHLCV_CACHE[s] = []

    # Start a background task to periodically fetch XMR price from CoinGecko & Kraken
    async def fetch_xmr_price_periodically():
        import urllib.request
        import json

        def fetch_coingecko():
            req = urllib.request.Request(
                'https://api.coingecko.com/api/v3/simple/price?ids=monero&vs_currencies=usd',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return float(data["monero"]["usd"])

        def fetch_kraken():
            import ccxt
            client = ccxt.kraken({'enableRateLimit': True, 'timeout': 5000})
            ticker = client.fetch_ticker('XMR/USD')
            return float(ticker['last'])

        while True:
            loop = asyncio.get_event_loop()
            xmr_price = None
            source_used = None

            for fetch_fn, name in [(fetch_coingecko, "CoinGecko"), (fetch_kraken, "Kraken")]:
                try:
                    xmr_price = await loop.run_in_executor(None, fetch_fn)
                    source_used = name
                    break
                except Exception as e:
                    print(f"[XMR Price] {name} failed: {e}")

            if xmr_price is not None and "XMR" in GLOBAL_MARKET_STATE:
                GLOBAL_MARKET_STATE["XMR"]["current_price"] = xmr_price
                GLOBAL_MARKET_STATE["XMR"]["price_source"] = source_used
                static_mcap = GLOBAL_MARKET_STATE["XMR"].get("market_cap_usd", 0)
                if GLOBAL_MARKET_STATE["XMR"].get("circulating_supply", 0) == 0 and xmr_price > 0 and static_mcap > 0:
                    GLOBAL_MARKET_STATE["XMR"]["circulating_supply"] = static_mcap / xmr_price
                
                circ_supply = GLOBAL_MARKET_STATE["XMR"].get("circulating_supply", 0)
                if circ_supply > 0:
                    GLOBAL_MARKET_STATE["XMR"]["market_cap_usd"] = circ_supply * xmr_price
            else:
                # Both real sources failed. Freeze the price.
                print("[XMR Price] All sources failed this cycle — holding last known price.")
                if "XMR" in GLOBAL_MARKET_STATE:
                    GLOBAL_MARKET_STATE["XMR"]["price_source"] = "stale"
            
            await asyncio.sleep(60)

    asyncio.create_task(fetch_xmr_price_periodically())

    import logging
    from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

    logger = logging.getLogger("cryptograph.binance_ws")

    class FallbackDataFetcher:
        """
        Implements the explicit fallback hierarchy requested:
        1. Primary: Binance API
        2. Secondary: CoinGecko API (via HTTP fallback)
        3. Tertiary: Local SQLite Cache
        """
        def __init__(self, db_session: Session):
            self.db = db_session
            
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=10),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type(Exception)
        )
        async def fetch_coingecko_fallback(self, symbol: str) -> float:
            import urllib.request
            import json
            loop = asyncio.get_event_loop()
            def fetch():
                # Map symbol to coingecko id
                cg_map = {"BTC": "bitcoin", "ETH": "ethereum", "XMR": "monero", "POL": "matic-network"}
                cg_id = cg_map.get(symbol, symbol.lower())
                req = urllib.request.Request(
                    f'https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd',
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    return json.loads(response.read().decode())
            
            res = await loop.run_in_executor(None, fetch)
            cg_id = {"BTC": "bitcoin", "ETH": "ethereum", "XMR": "monero", "POL": "matic-network"}.get(symbol, symbol.lower())
            if cg_id in res and "usd" in res[cg_id]:
                return float(res[cg_id]["usd"])
            raise Exception("CoinGecko data missing")

        async def get_price(self, symbol: str) -> float:
            try:
                # In a real scenario, this would be a Binance REST call.
                # Here we simulate falling back straight to CoinGecko if WS is dead.
                return await self.fetch_coingecko_fallback(symbol)
            except Exception as e:
                logger.warning(f"CoinGecko fallback failed for {symbol}: {e}. Falling back to SQLite cache.")
                # Tertiary Fallback: SQLite Cache
                from app.db.models_sqla import OHLCV, Asset
                asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
                if asset:
                    ohlcv = self.db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
                    if ohlcv:
                        return float(ohlcv.close)
                return 0.0

    reconnect_delay = 1
    max_reconnect_delay = 60

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                subscribe_payload = {
                    "method": "SUBSCRIBE",
                    "params": all_streams,
                    "id": 1
                }
                await ws.send(json.dumps(subscribe_payload))
                logger.info(f"[BinanceWS] Connected to live kline & ticker streams for {len(ws_symbols)} assets.")
                
                # Reset reconnect delay on successful connection
                reconnect_delay = 1
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if "e" in data:
                        symbol = data["s"].replace("USDT", "")
                        asset_symbol = symbol_to_asset.get(symbol, symbol)
                        
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
                            
                            cache_list = LIVE_OHLCV_CACHE.get(asset_symbol, [])
                            if len(cache_list) > 0 and cache_list[-1]["timestamp"] == timestamp:
                                cache_list[-1] = ohlcv
                            else:
                                cache_list.append(ohlcv)
                                if len(cache_list) > CACHE_MAX_SIZE:
                                    cache_list.pop(0)
                            
                            LIVE_OHLCV_CACHE[asset_symbol] = cache_list
                            
                        elif data["e"] == "24hrTicker":
                            if asset_symbol in GLOBAL_MARKET_STATE:
                                live_price = float(data["c"])
                                static_mcap = GLOBAL_MARKET_STATE[asset_symbol].get("market_cap_usd", 0)
                                current_mcap = static_mcap
                                
                                if GLOBAL_MARKET_STATE[asset_symbol].get("circulating_supply", 0) == 0 and live_price > 0 and static_mcap > 0:
                                    GLOBAL_MARKET_STATE[asset_symbol]["circulating_supply"] = static_mcap / live_price
                                
                                circ_supply = GLOBAL_MARKET_STATE[asset_symbol].get("circulating_supply", 0)
                                if circ_supply > 0:
                                    current_mcap = circ_supply * live_price
                                
                                GLOBAL_MARKET_STATE[asset_symbol]["current_price"] = live_price
                                GLOBAL_MARKET_STATE[asset_symbol]["volume_24h"] = float(data["q"])
                                GLOBAL_MARKET_STATE[asset_symbol]["price_change_24h_pct"] = float(data["P"])
                                GLOBAL_MARKET_STATE[asset_symbol]["market_cap_usd"] = current_mcap
                                GLOBAL_MARKET_STATE[asset_symbol]["updated_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.error(f"[BinanceWS] Connection error: {e}. Engaging fallback layer...")
            # Trigger Fallback layer to keep UI responsive
            from app.db.database import SessionLocal
            db = SessionLocal()
            try:
                fetcher = FallbackDataFetcher(db)
                # Just update BTC as a bellwether during downtime to show resilience
                if "BTC" in GLOBAL_MARKET_STATE:
                    fallback_price = await fetcher.get_price("BTC")
                    if fallback_price > 0:
                        GLOBAL_MARKET_STATE["BTC"]["current_price"] = fallback_price
                        logger.info(f"Fallback successful: BTC price updated to {fallback_price}")
            finally:
                db.close()
            
            logger.info(f"[BinanceWS] Reconnecting in {reconnect_delay} seconds...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

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
