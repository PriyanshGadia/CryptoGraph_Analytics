import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
import sys
from pathlib import Path

# Add project root and backend to path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from ml.models.forecast_model import (
    run_mean_reversion_forecast,
    run_ensemble_forecast,
    run_lstm_forecast,
    run_prophet_forecast
)

def test_mean_reversion_forecast():
    # Make a simple historical price series (length 60)
    prices = pd.Series([100.0 + i * 0.1 for i in range(60)])
    
    result = run_mean_reversion_forecast(prices, forecast_days=7)
    
    assert isinstance(result, dict)
    assert "forecast_prices" in result
    assert "lower_bound" in result
    assert "upper_bound" in result
    assert len(result["forecast_prices"]) == 7
    assert len(result["lower_bound"]) == 7
    assert len(result["upper_bound"]) == 7
    assert result["model_used"] == "Mean Reversion Baseline"
    
    # Assert lower bound <= forecast <= upper bound
    for p, l, u in zip(result["forecast_prices"], result["lower_bound"], result["upper_bound"]):
        assert l <= p <= u

@patch("ml.models.forecast_model.run_lstm_forecast")
@patch("ml.models.forecast_model.run_prophet_forecast")
def test_ensemble_forecast_both_successful(mock_prophet, mock_lstm):
    # Mock successful LSTM forecast
    mock_lstm.return_value = {
        "forecast_prices": [100.0, 102.0],
        "lower_bound": [98.0, 100.0],
        "upper_bound": [102.0, 104.0],
        "model_used": "LSTM"
    }
    # Mock successful Prophet forecast
    mock_prophet.return_value = {
        "forecast_prices": [101.0, 103.0],
        "lower_bound": [95.0, 97.0],
        "upper_bound": [107.0, 109.0],
        "model_used": "Prophet"
    }
    
    prices = pd.Series([100.0, 101.0])
    dates = pd.Series(pd.date_range("2026-07-01", periods=2))
    
    result = run_ensemble_forecast(prices, dates, forecast_days=2)
    
    assert result["ensemble"] is True
    assert "Inverse-Variance Weighted" in result["model_used"]
    assert len(result["forecast_prices"]) == 2
    
    # Calculate inverse-variance weight manually to verify
    # For day 1:
    # LSTM price = 100.0, upper = 102.0, lower = 98.0
    # LSTM width = 4.0, LSTM std = 4.0 / (2 * 1.96) = 1.0204, LSTM var = 1.0412
    # Prophet price = 101.0, upper = 107.0, lower = 95.0
    # Prophet width = 12.0, Prophet std = 12.0 / (2 * 1.96) = 3.0612, Prophet var = 9.3711
    # LSTM has much lower variance, so ensemble price should be closer to 100.0 than 101.0
    assert result["forecast_prices"][0] < 100.2
    assert result["forecast_prices"][0] > 99.9

@patch("ml.models.forecast_model.run_lstm_forecast")
@patch("ml.models.forecast_model.run_prophet_forecast")
def test_ensemble_forecast_fallback_baseline(mock_prophet, mock_lstm):
    # If both models fail, ensemble should revert to Mean Reversion Baseline
    mock_lstm.return_value = None
    mock_prophet.return_value = None
    
    prices = pd.Series([100.0] * 60)
    dates = pd.Series(pd.date_range("2026-07-01", periods=60))
    
    result = run_ensemble_forecast(prices, dates, forecast_days=7)
    
    assert result["model_used"] == "Mean Reversion Baseline"
    assert len(result["forecast_prices"]) == 7
