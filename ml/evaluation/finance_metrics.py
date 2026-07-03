"""Standalone finance metric functions. All accept pd.Series of daily returns."""

import pandas as pd
import numpy as np

def sharpe_ratio(returns: pd.Series, annualization: int = 252) -> float:
    """mean(r) / std(r) * sqrt(252). Returns 0 if std is 0."""
    std = returns.std()
    if pd.isna(std) or std == 0.0:
        return 0.0
    return float((returns.mean() / std) * np.sqrt(annualization))

def sortino_ratio(returns: pd.Series, annualization: int = 252) -> float:
    """mean(r) / std(downside_returns) * sqrt(252). Downside = returns < 0."""
    downside = returns[returns < 0]
    std = downside.std()
    if pd.isna(std) or std == 0.0:
        return 0.0
    return float((returns.mean() / std) * np.sqrt(annualization))

def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough percentage decline. Returns negative float."""
    # Clip returns to reasonable daily boundaries to prevent mathematical overflows
    clipped_returns = np.clip(returns.values, -0.99, 10.0)
    # Convert returns to cumulative wealth index
    wealth = np.cumprod(1 + clipped_returns)
    # Handle any inf/nan outputs safely
    wealth = np.nan_to_num(wealth, nan=1.0, posinf=1.0, neginf=1.0)
    # cummax requires pandas series or manual loop
    peaks = pd.Series(wealth).cummax().values
    drawdowns = (wealth - peaks) / (peaks + 1e-8)
    return float(drawdowns.min())

def profit_factor(returns: pd.Series) -> float:
    """sum(positive_returns) / abs(sum(negative_returns)). Returns inf if no losses."""
    pos_sum = returns[returns > 0].sum()
    neg_sum = returns[returns < 0].sum()
    if neg_sum == 0:
        return float('inf')
    return float(pos_sum / abs(neg_sum))

def win_rate(returns: pd.Series) -> float:
    """Fraction of days with positive return."""
    if len(returns) == 0:
        return 0.0
    wins = (returns > 0).sum()
    return float(wins / len(returns))

def compute_all_finance_metrics(returns: pd.Series) -> dict:
    """Returns all 5 metrics as a flat dict."""
    return {
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "profit_factor": profit_factor(returns),
        "win_rate": win_rate(returns)
    }
