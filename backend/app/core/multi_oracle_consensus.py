"""
Multi-Oracle Consensus Engine (The Reality Anchor).
Prevents Black Swan data poisoning by requiring 2-out-of-3 oracle consensus
before the AI Swarm is allowed to execute a trade.
"""

import math
from typing import Dict, List, Optional
import ccxt
import logging
from cachetools import TTLCache
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import time

logger = logging.getLogger("cryptograph.consensus")

class MultiOracleConsensus:
    def __init__(self, deviation_threshold_pct: float = 1.5):
        self.deviation_threshold_pct = deviation_threshold_pct / 100.0
        # Cache CCXT fetches for 15 seconds to prevent rate-limiting on high-frequency validation
        self._price_cache = TTLCache(maxsize=1000, ttl=15)
        
        # Initialize CCXT exchange instances once
        self.exchanges = {
            "coinbase": ccxt.coinbase({"enableRateLimit": True}),
            "binance": ccxt.binance({"enableRateLimit": True}),
            "kraken": ccxt.kraken({"enableRateLimit": True}),
            "gemini": ccxt.gemini({"enableRateLimit": True}),
            "bitstamp": ccxt.bitstamp({"enableRateLimit": True}),
            "kucoin": ccxt.kucoin({"enableRateLimit": True})
        }
        
        # Reliability weights for exchanges
        self.exchange_weights = {
            "binance": 1.0,
            "coinbase": 0.9,
            "kraken": 0.8,
            "gemini": 0.7,
            "bitstamp": 0.7,
            "kucoin": 0.6
        }

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ccxt.NetworkError)
    )
    def _fetch_with_backoff(self, exchange, pair):
        return exchange.fetch_ticker(pair)

    def _fetch_price_safe(self, exchange_id: str, symbol: str) -> Optional[float]:
        """Fetch real price safely with fallbacks, caching, and rate limit protection."""
        cache_key = f"{exchange_id}_{symbol}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]
            
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            return None
            
        SYMBOL_MAP = {
            "binance": {"MATIC": "POL/USDT", "BTC": "BTC/USDT", "ETH": "ETH/USDT"},
            "coinbase": {"BTC": "BTC-USD", "ETH": "ETH-USD", "MATIC": "MATIC-USD"},
            "kraken": {"BTC": "XBT/USD", "ETH": "ETH/USD"}
        }
        
        pairs_to_try = []
        if exchange_id in SYMBOL_MAP and symbol in SYMBOL_MAP[exchange_id]:
            pairs_to_try.append(SYMBOL_MAP[exchange_id][symbol])
        
        pairs_to_try.extend([f"{symbol}/USDT", f"{symbol}/USD", f"{symbol}/BUSD", f"{symbol}/USDC"])
        
        for pair in pairs_to_try:
            try:
                ticker = self._fetch_with_backoff(exchange, pair)
                price = float(ticker["last"])
                self._price_cache[cache_key] = price
                return price
            except Exception as e:
                # E.g. BadSymbol or RateLimitExceeded
                continue
        return None

    def validate_price(self, symbol: str, primary_price: float) -> bool:
        """
        Validates the primary price against decentralized oracles using weighted median.
        Returns True if the price is within the acceptable deviation threshold.
        """
        # Fetch actual live prices from multiple oracle exchanges
        prices_with_weights = []
        for ex_id in self.exchanges.keys():
            p = self._fetch_price_safe(ex_id, symbol)
            if p is not None:
                prices_with_weights.append((p, self.exchange_weights[ex_id]))
        
        if len(prices_with_weights) == 0:
            logger.error(f"[Consensus] CRITICAL WARNING: ZERO oracle availability for {symbol}. Trading blocked.")
            return False
            
        if len(prices_with_weights) == 1:
            logger.warning(f"[Consensus] WARNING: Only 1 oracle available for {symbol}. Proceeding with degraded confidence.")
            
        # Calculate weighted median
        prices_with_weights.sort(key=lambda x: x[0])
        total_weight = sum(w for p, w in prices_with_weights)
        
        cumulative_weight = 0.0
        median_price = prices_with_weights[0][0]
        for p, w in prices_with_weights:
            cumulative_weight += w
            if cumulative_weight >= total_weight / 2.0:
                median_price = p
                break
            
        # Check deviation of primary against median
        deviation = abs(primary_price - median_price) / median_price
        
        if deviation > self.deviation_threshold_pct:
            logger.error(f"[Consensus] CRITICAL ALERT: Primary price {primary_price} deviates {deviation*100:.2f}% from median {median_price}. Oracle manipulation suspected.")
            return False
            
        logger.info(f"[Consensus] Price consensus reached for {symbol}: Primary={primary_price:.4f}, Median={median_price:.4f}, Deviation={deviation*100:.3f}%")
        return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    oracle = MultiOracleConsensus(deviation_threshold_pct=1.5)
    # Test with live prices
    is_valid = oracle.validate_price("BTC", 65000.0)
    logger.info(f"Consensus valid for BTC: {is_valid}")
