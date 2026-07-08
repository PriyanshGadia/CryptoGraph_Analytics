import pytest
import pandas as pd
import numpy as np
import os
import sys

# Add root to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ml.models.forecast_model import run_ensemble_forecast

def test_inverse_variance_weighting():
    # Mock data
    prices = pd.Series([50000.0] * 60)
    dates = pd.date_range("2024-01-01", periods=60)
    
    # We just run the function. Since the actual models require training weights, we might need a mocked run_lstm_forecast
    # But since this is a basic test, we will monkeypatch the underlying functions
    import ml.models.forecast_model as fm
    
    def mock_lstm(p, f_days):
        return {
            "forecast_prices": [51000.0] * f_days,
            "lower_bound": [50000.0] * f_days,
            "upper_bound": [52000.0] * f_days
        }
        
    def mock_prophet(p, d, f_days):
        return {
            "forecast_prices": [52000.0] * f_days,
            "lower_bound": [49000.0] * f_days,  # wider variance
            "upper_bound": [55000.0] * f_days   # wider variance
        }
        
    original_lstm = fm.run_lstm_forecast
    original_prophet = fm.run_prophet_forecast
    
    try:
        fm.run_lstm_forecast = mock_lstm
        fm.run_prophet_forecast = mock_prophet
        
        result = fm.run_ensemble_forecast(prices, dates, 7)
        assert result is not None
        assert result["ensemble"] is True
        
        # LSTM sigma = (52000 - 51000) / 1.96 = 510.2
        # Prophet sigma = (55000 - 52000) / 1.96 = 1530.6
        # LSTM var is roughly 1/9th of Prophet var.
        # So LSTM should have roughly 90% weight, Prophet 10%.
        # Price should be closer to 51000 than 52000.
        weighted_price = result["forecast_prices"][0]
        assert 51000.0 <= weighted_price <= 51200.0, f"Weighted price {weighted_price} not dominated by LSTM"
        
    finally:
        fm.run_lstm_forecast = original_lstm
        fm.run_prophet_forecast = original_prophet
