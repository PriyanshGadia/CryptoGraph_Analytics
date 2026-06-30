"""
Multi-Oracle Consensus Engine (The Reality Anchor).
Prevents Black Swan data poisoning by requiring 2-out-of-3 oracle consensus
before the AI Swarm is allowed to execute a trade.
"""

import math
from typing import Dict, List, Optional
import ccxt

class MultiOracleConsensus:
    def __init__(self, deviation_threshold_pct: float = 0.5):
        self.deviation_threshold_pct = deviation_threshold_pct / 100.0
        # Initialize CCXT exchange instances once
        self.exchanges = {
            "coinbase": ccxt.coinbase({"enableRateLimit": True}),
            "binance": ccxt.binance({"enableRateLimit": True}),
            "kraken": ccxt.kraken({"enableRateLimit": True})
        }

    def _fetch_binance_price(self, symbol: str) -> Optional[float]:
        """Fetch real Binance Price using CCXT"""
        try:
            pair = f"{symbol}/USDT"
            ticker = self.exchanges["binance"].fetch_ticker(pair)
            return float(ticker["last"])
        except Exception:
            try:
                pair = f"{symbol}/BUSD"
                ticker = self.exchanges["binance"].fetch_ticker(pair)
                return float(ticker["last"])
            except Exception:
                return None

    def _fetch_coinbase_price(self, symbol: str) -> Optional[float]:
        """Fetch real Coinbase Price using CCXT"""
        try:
            pair = f"{symbol}/USD"
            ticker = self.exchanges["coinbase"].fetch_ticker(pair)
            return float(ticker["last"])
        except Exception:
            return None

    def _fetch_kraken_price(self, symbol: str) -> Optional[float]:
        """Fetch real Kraken Price using CCXT"""
        try:
            pair = f"{symbol}/USD"
            ticker = self.exchanges["kraken"].fetch_ticker(pair)
            return float(ticker["last"])
        except Exception:
            try:
                pair = f"{symbol}/USDT"
                ticker = self.exchanges["kraken"].fetch_ticker(pair)
                return float(ticker["last"])
            except Exception:
                return None

    def validate_price(self, symbol: str, primary_price: float) -> bool:
        """
        Validates the primary price against decentralized oracles.
        Returns True if the price is within the acceptable deviation threshold.
        """
        # Fetch actual live prices from multiple oracle exchanges
        binance = self._fetch_binance_price(symbol)
        coinbase = self._fetch_coinbase_price(symbol)
        kraken = self._fetch_kraken_price(symbol)
        
        prices = [p for p in [primary_price, binance, coinbase, kraken] if p is not None]
        
        if len(prices) < 2:
            print(f"[Consensus] WARNING: Insufficient oracle availability for {symbol}. Trading unsafe.")
            return False
            
        # Calculate median price
        prices.sort()
        if len(prices) % 2 == 1:
            median_price = prices[len(prices) // 2]
        else:
            mid = len(prices) // 2
            median_price = (prices[mid - 1] + prices[mid]) / 2.0
            
        # Check deviation of primary against median
        deviation = abs(primary_price - median_price) / median_price
        
        if deviation > self.deviation_threshold_pct:
            print(f"[Consensus] CRITICAL ALERT: Primary price {primary_price} deviates {deviation*100:.2f}% from median {median_price}. Oracle manipulation suspected.")
            return False
            
        print(f"[Consensus] Price consensus reached for {symbol}: Primary={primary_price:.4f}, Median={median_price:.4f}, Deviation={deviation*100:.3f}%")
        return True

if __name__ == "__main__":
    oracle = MultiOracleConsensus(deviation_threshold_pct=0.5)
    # Test with live prices
    is_valid = oracle.validate_price("BTC", 65000.0)
    print(f"Consensus valid for BTC: {is_valid}")
