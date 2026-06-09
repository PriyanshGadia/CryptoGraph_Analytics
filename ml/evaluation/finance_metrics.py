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
    # Convert returns to cumulative wealth index
    wealth = (1 + returns).cumprod()
    peaks = wealth.cummax()
    drawdowns = (wealth - peaks) / peaks
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
