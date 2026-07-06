"""Standalone finance metric functions. All accept pd.Series of daily returns."""

import pandas as pd
import numpy as np

CRYPTO_TRADING_DAYS = 365  # crypto markets trade every calendar day, unlike equities' 252


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.04, annualization: int = CRYPTO_TRADING_DAYS) -> float:
    daily_rf = risk_free_rate / annualization
    excess = returns - daily_rf
    std = excess.std()
    if pd.isna(std) or std == 0.0:
        return 0.0
    return float((excess.mean() / std) * np.sqrt(annualization))


def _downside_deviation(returns: pd.Series, target: float = 0.0) -> float:
    """Correct Sortino downside deviation: RMS of shortfalls below target,
    computed over ALL observations — not the std() of only the negative
    subset, which measures deviation from the wrong reference point."""
    shortfall = np.minimum(returns - target, 0.0)
    return float(np.sqrt(np.mean(np.square(shortfall))))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.04, annualization: int = CRYPTO_TRADING_DAYS) -> float:
    daily_rf = risk_free_rate / annualization
    excess = returns - daily_rf
    downside_dev = _downside_deviation(returns, target=daily_rf)
    if downside_dev == 0.0:
        return 0.0
    return float((excess.mean() / downside_dev) * np.sqrt(annualization))


def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough percentage decline. Returns negative float."""
    clipped_returns = np.clip(returns.values, -0.99, 10.0)
    wealth = np.cumprod(1 + clipped_returns)
    wealth = np.nan_to_num(wealth, nan=1.0, posinf=1.0, neginf=1.0)
    peaks = pd.Series(wealth).cummax().values
    drawdowns = (wealth - peaks) / (peaks + 1e-8)
    return float(drawdowns.min())


def profit_factor(returns: pd.Series) -> float:
    """sum(positive_returns) / abs(sum(negative_returns)). Caps at 999.0 if no losses."""
    pos_sum = returns[returns > 0].sum()
    neg_sum = returns[returns < 0].sum()
    if neg_sum == 0:
        return 999.0 if pos_sum > 0 else 0.0
    return float(pos_sum / abs(neg_sum))


def win_rate(returns: pd.Series) -> float:
    """Fraction of days with positive return."""
    if len(returns) == 0:
        return 0.0
    wins = (returns > 0).sum()
    return float(wins / len(returns))


def compute_all_finance_metrics(returns: pd.Series, risk_free_rate: float = 0.04) -> dict:
    """Returns all 5 metrics as a flat dict."""
    return {
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate=risk_free_rate),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate=risk_free_rate),
        "max_drawdown": max_drawdown(returns),
        "profit_factor": profit_factor(returns),
        "win_rate": win_rate(returns)
    }
