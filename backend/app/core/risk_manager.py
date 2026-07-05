"""
RiskManagerCore

Acts as the mathematical safeguard sitting above the CIO Agent.
Uses hard-coded quantitative circuit breakers (Kelly Criterion, Max Drawdown, Volatility)
to veto trades hallucinated by the LLM.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models_sqla import PortfolioState, TradeHistory, OHLCV

class RiskManagerCore:
    def __init__(self, db: Session):
        self.db = db
        # Risk parameters
        self.max_drawdown_limit = 0.15  # 15% Max Drawdown halts all buying
        self.max_volatility_7d = 0.40    # 40% 7-day volatility halts buying
        self.base_kelly_fraction = 0.05  # Base 5% of portfolio

    def evaluate_trade(self, symbol: str, cio_decision: str, confidence: float, current_portfolio: PortfolioState) -> Dict[str, Any]:
        """
        Evaluates the CIO's proposed decision against mathematical risk rules.
        Returns:
            {"approved": bool, "reasoning": str, "suggested_allocation_usd": float}
        """
        if cio_decision != "EXECUTE_BUY":
            # We don't block sells or holds. We only risk-manage buys.
            return {"approved": True, "reasoning": "RiskManager: Non-buy actions are auto-approved.", "suggested_allocation_usd": 0.0}

        # 1. Check Portfolio Drawdown Circuit Breaker
        all_portfolios = self.db.query(PortfolioState).order_by(PortfolioState.timestamp.asc()).all()
        if all_portfolios:
            peak = max(p.total_value for p in all_portfolios)
            current_drawdown = (peak - current_portfolio.total_value) / peak
            if current_drawdown > self.max_drawdown_limit:
                return {
                    "approved": False,
                    "reasoning": f"RiskManager VETO: Portfolio drawdown ({current_drawdown*100:.1f}%) exceeds hard limit ({self.max_drawdown_limit*100}%). Auto-halt engaged.",
                    "suggested_allocation_usd": 0.0
                }

        # 2. Check Asset Volatility Circuit Breaker
        # Fetch last 7 days of OHLCV to calculate rough volatility
        from datetime import datetime, timedelta, timezone
        from app.db.models_sqla import Asset
        
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            return {"approved": False, "reasoning": f"RiskManager VETO: Asset {symbol} not found.", "suggested_allocation_usd": 0.0}
            
        recent_ohlcv = self.db.query(OHLCV).filter(
            OHLCV.asset_id == asset.id
        ).order_by(desc(OHLCV.timestamp)).limit(7).all()
        
        if len(recent_ohlcv) >= 2:
            closes = [r.close for r in recent_ohlcv]
            high_price = max(closes)
            low_price = min(closes)
            # Simple approximation of 7-day volatility range
            vol_range = (high_price - low_price) / low_price
            if vol_range > self.max_volatility_7d:
                return {
                    "approved": False,
                    "reasoning": f"RiskManager VETO: Asset 7-day volatility ({vol_range*100:.1f}%) exceeds hard limit ({self.max_volatility_7d*100}%).",
                    "suggested_allocation_usd": 0.0
                }

        # 3. Position Sizing (Kelly Criterion with 15% Allocation Cap & Cash Buffer Safeguard)
        # Normalize confidence score: handle both percentage (85.5) and ratio (0.85) inputs
        conf_norm = confidence / 100.0 if confidence > 1.0 else confidence
        conf_norm = max(0.0, min(1.0, conf_norm))
        
        # Baseline for 3-class direction models is 33.3%, while binary models baseline is 50.0%
        baseline = 0.333 if conf_norm < 0.50 else 0.50
        edge = max(0.0, conf_norm - baseline)
        multiplier = min(2.0, max(0.4, edge / 0.10 if baseline == 0.333 else edge / 0.50))
        
        # Base allocation: 5% of total portfolio value scaled by model edge multiplier
        base_target_fraction = 0.05 * multiplier
        # Hard cap: maximum 7% of portfolio total value per position
        target_fraction = min(0.07, base_target_fraction)
        
        suggested_allocation = current_portfolio.total_value * target_fraction
        
        # Cash Buffer Safeguard: Preserve at least 5% of total portfolio value in unallocated cash
        min_cash_reserve = current_portfolio.total_value * 0.05
        max_available_for_trade = max(0.0, current_portfolio.cash_balance - min_cash_reserve)
        
        if max_available_for_trade < 100.0:
            return {
                "approved": False,
                "reasoning": f"RiskManager VETO: Insufficient unreserved cash balance (${current_portfolio.cash_balance:.2f}) to open new buy position.",
                "suggested_allocation_usd": 0.0
            }

        suggested_allocation = min(suggested_allocation, max_available_for_trade)

        return {
            "approved": True, 
            "reasoning": f"RiskManager APPROVED: Position sizing set to ${suggested_allocation:,.2f} based on {conf_norm*100:.1f}% confidence.",
            "suggested_allocation_usd": suggested_allocation
        }
