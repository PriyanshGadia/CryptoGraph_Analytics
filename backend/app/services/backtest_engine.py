"""
Institutional Tear Sheet Engine (Vectorized Backtester)

Generates compliance-ready financial performance metrics:
- Annualized Return
- Maximum Drawdown
- Sharpe Ratio (Risk-Adjusted Return)
- Sortino Ratio (Downside Risk)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import PortfolioState
from ml.evaluation.finance_metrics import sharpe_ratio, sortino_ratio


import os
import requests
from datetime import datetime, timedelta, timezone

def get_current_risk_free_rate() -> float:
    """Fetch from FRED API or use configurable env var."""
    try:
        # Note: FRED API requires an API key, we fallback to ENV or default if not available
        rate_str = os.getenv("RISK_FREE_RATE")
        if rate_str:
            return float(rate_str)
        # Attempt public endpoint or fallback
        # This is a mock since FRED requires an API key in reality
        return 0.04
    except Exception:
        return 0.04

def generate_tear_sheet(
    db: Session, 
    risk_free_rate: float = None,
    maker_fee: float = 0.001,      # 0.1% Binance VIP 0 maker fee
    slippage: float = 0.002,       # 0.2% assumed slippage
    daily_turnover: float = 0.10   # Assume 10% of portfolio value is traded daily
) -> Dict[str, Any]:
    if risk_free_rate is None:
        risk_free_rate = get_current_risk_free_rate()
    """
    Generates institutional-grade backtest metrics by analyzing the historical 
    PortfolioState table over a windowed period to maintain high query efficiency.
    Incorporates realistic trading costs (fees + slippage) applied to daily turnover.
    """
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    states = db.query(PortfolioState).filter(
        PortfolioState.timestamp >= ninety_days_ago
    ).order_by(PortfolioState.timestamp.asc()).all()

    if len(states) < 2:
        # Fallback to the last 100 snapshots if data is sparse
        subq = db.query(PortfolioState.id).order_by(PortfolioState.timestamp.desc()).limit(100).subquery()
        states = db.query(PortfolioState).filter(PortfolioState.id.in_(subq)).order_by(PortfolioState.timestamp.asc()).all()
    
    if len(states) < 2:
        return {"error": "Not enough portfolio data to generate a tear sheet."}
        
    data = []
    for s in states:
        data.append({
            "date": pd.to_datetime(s.timestamp).tz_localize(None),
            "total_value": s.total_value,
            "btc_benchmark": s.btc_benchmark_value
        })
        
    df = pd.DataFrame(data)
    df.set_index("date", inplace=True)
    
    # Calculate daily returns
    raw_returns = df['total_value'].pct_change()
    
    # Apply Realistic Trading Costs (Fees + Slippage on turned-over capital)
    daily_trading_cost_pct = daily_turnover * (maker_fee + slippage)
    df['portfolio_return'] = raw_returns - daily_trading_cost_pct
    
    df['btc_return'] = df['btc_benchmark'].pct_change()
    df = df.dropna()
    
    if len(df) == 0:
        return {"error": "Insufficient varying data for metrics."}
        
    # --- Metrics Calculations ---
    # 1. Annualized Return (Assuming crypto trades 365 days a year)
    days = (df.index.max() - df.index.min()).days
    if days < 1:
        days = 1 # Prevent division by zero for intraday testing
        
    # Recalculate total return from the friction-adjusted daily returns
    total_return = (1 + df['portfolio_return']).prod() - 1
    annualized_return = (1 + total_return) ** (365 / days) - 1
    
    btc_total_return = (df['btc_benchmark'].iloc[-1] / df['btc_benchmark'].iloc[0]) - 1
    btc_annualized_return = (1 + btc_total_return) ** (365 / days) - 1

    # 2. Maximum Drawdown
    cumulative_returns = (1 + df['portfolio_return']).cumprod()
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown = drawdown.min()

    # 3. Sharpe & Sortino Ratios (Single Source of Truth from finance_metrics)
    sharpe = sharpe_ratio(df['portfolio_return'], risk_free_rate=risk_free_rate)
    sortino = sortino_ratio(df['portfolio_return'], risk_free_rate=risk_free_rate)
        
    # 4. Alpha & Beta (against BTC benchmark)
    covariance = df[['portfolio_return', 'btc_return']].cov().iloc[0, 1]
    btc_variance = df['btc_return'].var()
    
    beta = 0.0
    if btc_variance > 0:
        beta = covariance / btc_variance
        
    alpha = annualized_return - (risk_free_rate + beta * (btc_annualized_return - risk_free_rate))

    return {
        "days_active": days,
        "total_return_pct": total_return * 100,
        "annualized_return_pct": annualized_return * 100,
        "btc_annualized_return_pct": btc_annualized_return * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "alpha_pct": alpha * 100,
        "beta": beta
    }


def run_asset_backtest(
    db: Session,
    symbol: str,
    start_date: str,
    end_date: str,
    model_version: str = "stgcn-v1.0",
    starting_capital: float = 10000.0,
    confidence_threshold: float = 0.65,
    maker_fee: float = 0.001,
    slippage: float = 0.002
) -> Dict[str, Any]:
    """
    Runs a simulation over historical predictions and actual price data for a single symbol
    over a time range, calculating realistic trading performance metrics.
    """
    from app.db.models import Asset, Prediction, OHLCV
    from datetime import datetime, timezone
    
    # Resolve asset
    asset = db.query(Asset).filter(Asset.symbol == symbol.upper()).first()
    if not asset:
        return {"error": f"Asset {symbol} not found."}
        
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}
        
    # Get all predictions for this asset in range, ordered by timestamp
    preds = db.query(Prediction).filter(
        Prediction.asset_id == asset.id,
        Prediction.timestamp >= start_dt,
        Prediction.timestamp <= end_dt
    ).order_by(Prediction.timestamp.asc()).all()
    
    if not preds:
        return {"error": "No predictions found for this asset in the specified timeframe."}
        
    # Get all price bars for this asset in range, ordered by timestamp
    bars = db.query(OHLCV).filter(
        OHLCV.asset_id == asset.id,
        OHLCV.timestamp >= start_dt,
        OHLCV.timestamp <= end_dt
    ).order_by(OHLCV.timestamp.asc()).all()
    
    if not bars:
        return {"error": "No price history (OHLCV) found for this asset in the specified timeframe."}
        
    # Map predictions by date string (YYYY-MM-DD)
    pred_map = {}
    for p in preds:
        date_key = p.timestamp.strftime("%Y-%m-%d") if hasattr(p.timestamp, "strftime") else str(p.timestamp)[:10]
        pred_map[date_key] = p
        
    # Map price bars by date string
    bar_map = {}
    for b in bars:
        date_key = b.timestamp.strftime("%Y-%m-%d") if hasattr(b.timestamp, "strftime") else str(b.timestamp)[:10]
        bar_map[date_key] = b
        
    dates = sorted(list(set(pred_map.keys()) & set(bar_map.keys())))
    if len(dates) < 2:
        return {"error": "Not enough matching prediction and price data dates for simulation."}
        
    portfolio_value = starting_capital
    holding = 0.0 # Number of tokens held
    cash = starting_capital
    
    # Tracks daily equity curve
    equity_curve = []
    daily_returns = []
    
    # Strat parameters
    transaction_cost = maker_fee + slippage
    
    # Simulation loop
    for i in range(len(dates)):
        today_str = dates[i]
        bar = bar_map[today_str]
        pred = pred_map[today_str]
        
        # Current price
        price = bar.close
        
        # Record equity value at start of day
        current_equity = cash + (holding * price)
        equity_curve.append({
            "date": today_str,
            "equity": current_equity
        })
        
        # Decide action based on signal
        direction = pred.direction or "neutral"
        conf = pred.confidence or 0.0
        
        # Signals: 'up' or 'strong_up' with sufficient confidence
        should_long = direction in ["up", "strong_up"] and conf >= confidence_threshold
        
        if should_long:
            # If not already fully holding
            if cash > 0:
                # Buy token
                buy_value = cash * (1 - transaction_cost)
                holding = buy_value / price
                cash = 0.0
        else:
            # Sell token if holding
            if holding > 0:
                # Sell token
                sell_value = (holding * price) * (1 - transaction_cost)
                cash = sell_value
                holding = 0.0
                
        # End of day daily return calculation
        if i > 0:
            prev_equity = equity_curve[i-1]["equity"]
            ret = (current_equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
            daily_returns.append(ret)
            
    # Calculate performance metrics
    total_return = (portfolio_value - starting_capital) / starting_capital
    if equity_curve:
        final_equity = cash + (holding * bar_map[dates[-1]].close)
        total_return = (final_equity - starting_capital) / starting_capital
        
    # Maximum drawdown
    peak = starting_capital
    max_dd = 0.0
    for eq in equity_curve:
        val = eq["equity"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd
            
    # Sharpe & Sortino ratios (using finance_metrics logic)
    r_series = pd.Series(daily_returns) if daily_returns else pd.Series([0.0])
    s_ratio = sharpe_ratio(r_series, risk_free_rate=0.04)
    sort_ratio = sortino_ratio(r_series, risk_free_rate=0.04)
    
    # Calculate Win Rate (percentage of positive return days)
    pos_days = sum(1 for r in daily_returns if r > 0)
    win_rate = (pos_days / len(daily_returns)) * 100 if daily_returns else 0.0
    
    # Benchmark return (simple buy and hold of the same asset)
    start_price = bar_map[dates[0]].close
    end_price = bar_map[dates[-1]].close
    benchmark_return = (end_price - start_price) / start_price if start_price > 0 else 0.0
    
    return {
        "status": "completed",
        "symbol": symbol.upper(),
        "timeframe": f"{dates[0]} to {dates[-1]}",
        "metrics": {
            "sharpe_ratio": round(s_ratio, 2),
            "sortino_ratio": round(sort_ratio, 2),
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(max_dd, 4),
            "total_return_pct": round(total_return * 100, 2),
            "benchmark_return_pct": round(benchmark_return * 100, 2),
            "days_active": len(dates)
        },
        "model_version": model_version
    }


if __name__ == "__main__":
    from app.db.database import SessionLocal
    db = SessionLocal()
    metrics = generate_tear_sheet(db)
    print("=== Institutional Tear Sheet ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"{k}: {v:.2f}")
        else:
            print(f"{k}: {v}")
