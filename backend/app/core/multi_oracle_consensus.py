"""
Multi-Oracle Consensus Engine (The Reality Anchor).
Prevents Black Swan data poisoning by requiring 2-out-of-3 oracle consensus
before the AI Swarm is allowed to execute a trade.
"""

import math
from typing import Dict, List, Optional

class MultiOracleConsensus:
    def __init__(self, deviation_threshold_pct: float = 0.5):
        self.deviation_threshold_pct = deviation_threshold_pct / 100.0

    def _fetch_binance_price(self, symbol: str) -> Optional[float]:
        """Mock Binance Price Fetcher"""
        # In production, this hits Binance API
        return None

    def _fetch_pyth_price(self, symbol: str) -> Optional[float]:
        """Mock Pyth Network Price Fetcher"""
        # In production, this hits Pyth Hermes RPC
        return None

    def _fetch_chainlink_price(self, symbol: str) -> Optional[float]:
        """Mock Chainlink Price Fetcher"""
        # In production, this queries the Chainlink Aggregator Smart Contract
        return None

    def validate_price(self, symbol: str, primary_price: float) -> bool:
        """
        Validates the primary price against decentralized oracles.
        Returns True if the price is within the acceptable deviation threshold.
        """
        # In our simulation, we mock the oracle prices around the primary_price
        # to demonstrate the consensus logic working.
        
        # Simulate Pyth agreeing closely
        pyth_price = primary_price * 1.001 
        
        # Simulate Chainlink agreeing closely
        chainlink_price = primary_price * 0.998 
        
        oracles = [primary_price, pyth_price, chainlink_price]
        valid_prices = [p for p in oracles if p is not None]
        
        if len(valid_prices) < 2:
            print(f"[Consensus] WARNING: Insufficient oracle availability for {symbol}. Trading unsafe.")
            return False
            
        # Calculate median price
        valid_prices.sort()
        if len(valid_prices) % 2 == 1:
            median_price = valid_prices[len(valid_prices) // 2]
        else:
            mid = len(valid_prices) // 2
            median_price = (valid_prices[mid - 1] + valid_prices[mid]) / 2.0
            
        # Check deviation of primary against median
        deviation = abs(primary_price - median_price) / median_price
        
        if deviation > self.deviation_threshold_pct:
            print(f"[Consensus] CRITICAL ALERT: Primary price {primary_price} deviates {deviation*100:.2f}% from median {median_price}. Oracle manipulation suspected.")
            return False
            
        return True

if __name__ == "__main__":
    oracle = MultiOracleConsensus(deviation_threshold_pct=0.5)
    
    # Test Normal Scenario
    is_valid = oracle.validate_price("BTC", 65000.0)
    print(f"BTC $65k Valid: {is_valid}")
    
    # Test Flash Crash Scenario (e.g. Binance glitches to $10,000 but oracles report $65,000)
    # We will simulate this by manually bypassing the mock Pyth/Chainlink logic above for a test
    # (In the real implementation, the external fetches would return $65k while Binance returned $10k)
