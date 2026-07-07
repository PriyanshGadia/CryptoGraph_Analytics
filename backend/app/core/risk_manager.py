"""
RiskManagerCore

Acts as the mathematical safeguard sitting above the CIO Agent.
Uses quantitative circuit breakers and Fractional Kelly Criterion position sizing
(f* = (p*b - q)/b) to regulate trades recommended by the multi-agent swarm.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models_sqla import PortfolioState, TradeHistory, OHLCV, Asset
from datetime import datetime, timedelta, timezone


class RiskManagerCore:
    def __init__(
        self,
        db: Session,
        max_drawdown_limit: float = 0.35,      # 35% Max Drawdown halts all buying
        max_volatility_7d: float = 0.40,        # 40% 7-day volatility halts buying
        payoff_ratio: float = 2.0,              # Expected reward-to-risk ratio (b)
        kelly_fraction: float = 0.5,            # Fractional Kelly multiplier (Half-Kelly)
        max_position_cap: float = 0.07,         # Hard cap per position (7% max allocation)
        min_cash_reserve_pct: float = 0.05,     # Cash reserve buffer (5% minimum)
    ):
        self.db = db
        self.max_drawdown_limit = max_drawdown_limit
        self.max_volatility_7d = max_volatility_7d
        self.payoff_ratio = payoff_ratio
        self.kelly_fraction = kelly_fraction
        self.max_position_cap = max_position_cap
        self.min_cash_reserve_pct = min_cash_reserve_pct

    def evaluate_trade(
        self,
        symbol: str,
        cio_decision: str,
        confidence: float,
        current_portfolio: PortfolioState,
        baseline_prob: float = 0.3333
    ) -> Dict[str, Any]:
        """
        Evaluates the CIO's proposed decision against mathematical risk rules.
        Returns:
            {"approved": bool, "reasoning": str, "suggested_allocation_usd": float}
        """
        if cio_decision != "EXECUTE_BUY":
            # We don't block sells or holds. We only risk-manage buys.
            return {
                "approved": True,
                "reasoning": "RiskManager: Non-buy actions are auto-approved.",
                "suggested_allocation_usd": 0.0
            }

        # 1. Check Portfolio Drawdown Circuit Breaker (Global High-Water Mark)
        from sqlalchemy import func
        peak = self.db.query(func.max(PortfolioState.total_value)).scalar()
        if peak is None:
            peak = current_portfolio.total_value

        if peak > 0:
            current_drawdown = (peak - current_portfolio.total_value) / peak
            if current_drawdown > self.max_drawdown_limit:
                return {
                    "approved": False,
                    "reasoning": f"RiskManager VETO: Portfolio drawdown ({current_drawdown*100:.1f}%) exceeds hard limit ({self.max_drawdown_limit*100}%). Auto-halt engaged.",
                    "suggested_allocation_usd": 0.0
                }

        # 2. Check Asset Volatility Circuit Breaker
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            return {"approved": False, "reasoning": f"RiskManager VETO: Asset {symbol} not found.", "suggested_allocation_usd": 0.0}

        recent_ohlcv = self.db.query(OHLCV).filter(
            OHLCV.asset_id == asset.id
        ).order_by(desc(OHLCV.timestamp)).limit(7).all()

        if len(recent_ohlcv) >= 2:
            import numpy as np
            closes = [r.close for r in recent_ohlcv]
            returns = np.diff(np.log(closes))
            vol_range = float(np.std(returns) * np.sqrt(365))  # Annualized volatility
            if vol_range > self.max_volatility_7d:
                return {
                    "approved": False,
                    "reasoning": f"RiskManager VETO: Asset 7-day volatility ({vol_range*100:.1f}%) exceeds hard limit ({self.max_volatility_7d*100}%).",
                    "suggested_allocation_usd": 0.0
                }

        # 3. Position Sizing (True Fractional Kelly Criterion: f* = (p*b - q)/b with Dynamic Baseline Edge Check)
        import math
        raw_p = max(0.0, min(1.0, float(confidence)))
        # Apply Platt/Temperature scaling via Sigmoid to calibrate raw score into a true probability
        p = 1.0 / (1.0 + math.exp(-(raw_p - 0.5) * 10.0))

        # Dynamic Edge Check: Verify model confidence exceeds model's baseline probability
        if p <= baseline_prob:
            return {
                "approved": False,
                "reasoning": f"RiskManager VETO: Model confidence ({p*100:.1f}%) does not exceed dynamic baseline probability ({baseline_prob*100:.1f}%). Zero statistical edge.",
                "suggested_allocation_usd": 0.0
            }

        q = 1.0 - p                        # Loss probability
        
        # Calculate dynamic b (payoff ratio) using expected return over volatility
        from sqlalchemy import text as sa_text
        tech_row = self.db.execute(sa_text("""
            SELECT returns_1d, volatility_7d
            FROM technical_features
            WHERE asset_id = :aid
            ORDER BY timestamp DESC LIMIT 1
        """), {"aid": asset.id}).fetchone()
        
        expected_return = 0.02 # fallback 2%
        volatility = 0.05      # fallback 5%
        
        if tech_row and tech_row[0] is not None and tech_row[1] is not None:
            # We assume a daily expected return bounded for safety
            expected_return = max(0.001, abs(float(tech_row[0]))) 
            volatility = max(0.001, float(tech_row[1]))
            
        b = expected_return / volatility
        # Sanity cap on b to prevent extreme sizing
        b = max(0.5, min(10.0, b))

        raw_kelly = (p * b - q) / b if b > 0 else 0.0
        raw_kelly = max(0.0, raw_kelly)

        # Regime-dependent Kelly sizing
        # In highly volatile regimes, we reduce the kelly fraction
        regime_adjusted_fraction = self.kelly_fraction
        if volatility > 0.15:      # High volatility
            regime_adjusted_fraction *= 0.5
        elif volatility > 0.05:    # Medium volatility
            regime_adjusted_fraction *= 0.8
            
        # Apply regime-adjusted Fractional Kelly
        kelly_allocation = raw_kelly * regime_adjusted_fraction

        # Hard cap position size
        target_fraction = min(self.max_position_cap, kelly_allocation)

        suggested_allocation = current_portfolio.total_value * target_fraction

        # 4. Cash Buffer Safeguard
        min_cash_reserve = current_portfolio.total_value * self.min_cash_reserve_pct
        max_available_for_trade = max(0.0, current_portfolio.cash_balance - min_cash_reserve)

        if max_available_for_trade < 100.0 or suggested_allocation <= 0.0:
            return {
                "approved": False,
                "reasoning": f"RiskManager VETO: Insufficient unreserved cash balance (${current_portfolio.cash_balance:.2f}) or Kelly fraction zero for new buy position.",
                "suggested_allocation_usd": 0.0
            }

        suggested_allocation = min(suggested_allocation, max_available_for_trade)

        return {
            "approved": True,
            "reasoning": f"RiskManager APPROVED: Kelly position sizing set to ${suggested_allocation:,.2f} based on {p*100:.1f}% confidence, b={b:.2f}, vol={volatility:.2f}.",
            "suggested_allocation_usd": suggested_allocation
        }
