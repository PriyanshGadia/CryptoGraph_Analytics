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
from app.db.models_sqla import PortfolioState
from ml.evaluation.finance_metrics import sharpe_ratio, sortino_ratio


def generate_tear_sheet(db: Session, risk_free_rate: float = 0.04) -> Dict[str, Any]:
    """
    Generates institutional-grade backtest metrics by analyzing the historical 
    PortfolioState table.
    """
    states = db.query(PortfolioState).order_by(PortfolioState.timestamp.asc()).all()
    
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
    df['portfolio_return'] = df['total_value'].pct_change()
    df['btc_return'] = df['btc_benchmark'].pct_change()
    df = df.dropna()
    
    if len(df) == 0:
        return {"error": "Insufficient varying data for metrics."}
        
    # --- Metrics Calculations ---
    # 1. Annualized Return (Assuming crypto trades 365 days a year)
    days = (df.index.max() - df.index.min()).days
    if days < 1:
        days = 1 # Prevent division by zero for intraday testing
        
    total_return = (df['total_value'].iloc[-1] / df['total_value'].iloc[0]) - 1
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
