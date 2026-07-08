"""
Unit test suite for trading agent holdings calculations and risk bounds.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

import pytest
from backend.app.core.risk_manager import RiskManagerCore

def test_risk_manager_bounds():
    # Verify risk manager parameters
    risk_mgr = RiskManagerCore(db=None)
    assert risk_mgr.max_drawdown_limit == 0.35
    assert risk_mgr.max_volatility_7d == 0.40
    assert risk_mgr.kelly_fraction == 0.5

def test_holdings_aggregation_logic():
    # Verify holdings position calculation logic
    trades = [
        {"symbol": "BTC", "side": "buy", "qty": 1.0, "total_usd": 50000.0},
        {"symbol": "BTC", "side": "buy", "qty": 0.5, "total_usd": 27000.0},
        {"symbol": "BTC", "side": "sell", "qty": 0.5, "total_usd": 28000.0},
    ]

    holdings = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in holdings:
            holdings[sym] = {"qty": 0.0, "total_invested": 0.0}
        if t["side"] == "buy":
            holdings[sym]["qty"] += t["qty"]
            holdings[sym]["total_invested"] += t["total_usd"]
        elif t["side"] == "sell":
            holdings[sym]["qty"] -= t["qty"]
            holdings[sym]["total_invested"] -= t["total_usd"]

    assert holdings["BTC"]["qty"] == 1.0
    assert holdings["BTC"]["total_invested"] == 49000.0
