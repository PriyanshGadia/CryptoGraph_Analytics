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
        max_drawdown_limit: float = 0.15,      # 15% Max Drawdown halts all buying
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

        # 1. Check Portfolio Drawdown Circuit Breaker (30-day rolling window)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_portfolios = self.db.query(PortfolioState).filter(
            PortfolioState.timestamp >= thirty_days_ago
        ).order_by(PortfolioState.timestamp.asc()).all()

        if not recent_portfolios:
            # Fallback to most recent 50 portfolio state snapshots
            subq = self.db.query(PortfolioState.id).order_by(PortfolioState.timestamp.desc()).limit(50).subquery()
            recent_portfolios = self.db.query(PortfolioState).filter(PortfolioState.id.in_(subq)).order_by(PortfolioState.timestamp.asc()).all()

        if recent_portfolios:
            peak = max(p.total_value for p in recent_portfolios)
            current_drawdown = (peak - current_portfolio.total_value) / peak if peak > 0 else 0.0
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
            closes = [r.close for r in recent_ohlcv]
            high_price = max(closes)
            low_price = min(closes)
            vol_range = (high_price - low_price) / low_price if low_price > 0 else 0.0
            if vol_range > self.max_volatility_7d:
                return {
                    "approved": False,
                    "reasoning": f"RiskManager VETO: Asset 7-day volatility ({vol_range*100:.1f}%) exceeds hard limit ({self.max_volatility_7d*100}%).",
                    "suggested_allocation_usd": 0.0
                }

        # 3. Position Sizing (True Fractional Kelly Criterion: f* = (p*b - q)/b with Dynamic Baseline Edge Check)
        p = max(0.0, min(1.0, float(confidence)))  # Win probability

        # Dynamic Edge Check: Verify model confidence exceeds model's baseline probability
        if p <= baseline_prob:
            return {
                "approved": False,
                "reasoning": f"RiskManager VETO: Model confidence ({p*100:.1f}%) does not exceed dynamic baseline probability ({baseline_prob*100:.1f}%). Zero statistical edge.",
                "suggested_allocation_usd": 0.0
            }

        q = 1.0 - p                        # Loss probability
        b = self.payoff_ratio              # Win/Loss payoff ratio

        raw_kelly = (p * b - q) / b if b > 0 else 0.0
        raw_kelly = max(0.0, raw_kelly)

        # Apply Half-Kelly (or configured fraction) to prevent over-betting under parameter uncertainty
        kelly_allocation = raw_kelly * self.kelly_fraction

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
            "reasoning": f"RiskManager APPROVED: Kelly position sizing set to ${suggested_allocation:,.2f} based on {conf_norm*100:.1f}% confidence.",
            "suggested_allocation_usd": suggested_allocation
        }
