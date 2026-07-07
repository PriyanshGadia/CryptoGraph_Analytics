"""
LSTM + Prophet ensemble for 60-day lookback, 7-day forecast.
Called on-demand by the FastAPI forecast endpoint.
"""
import numpy as np
import pandas as pd
from typing import Optional

_GLOBAL_LSTM_MODEL = None
_GLOBAL_LSTM_LOOKBACK = 14

def run_lstm_forecast(
    prices: pd.Series,  # 60 days of close prices, daily
    forecast_days: int = 30
) -> dict:
    """
    Runs LSTM forecast using a pre-trained global model.
    """
    global _GLOBAL_LSTM_MODEL, _GLOBAL_LSTM_LOOKBACK
    
    price_array = prices.values.astype(np.float32)
    price_min   = price_array.min()
    price_max   = price_array.max()
    price_range = price_max - price_min if price_max > price_min else 1.0
    normalized  = (price_array - price_min) / price_range
    
    try:
        import torch
        import torch.nn as nn
        import os
        from pathlib import Path
        
        class LSTMForecaster(nn.Module):
            def __init__(self, hidden_size=64, num_layers=2, dropout=0.1):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=1,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0.0
                )
                self.fc = nn.Sequential(
                    nn.Linear(hidden_size, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1)
                )
            
            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :]).squeeze(-1)
                
        if _GLOBAL_LSTM_MODEL is None:
            # Search for pre-trained model checkpoint
            ckpt_path = None
            possible_paths = [
                Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts" / "best_lstm.pt",
                Path(__file__).resolve().parent / "best_lstm.pt",
                Path("ml/artifacts/best_lstm.pt"),
                Path("../ml/artifacts/best_lstm.pt")
            ]
            for p in possible_paths:
                if p.exists() and p.is_file():
                    ckpt_path = p
                    break
                    
            if ckpt_path is None:
                raise FileNotFoundError("Pre-trained LSTM model checkpoint not found.")
                
            checkpoint = torch.load(str(ckpt_path), map_location="cpu")
            model = LSTMForecaster()
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()
            
            _GLOBAL_LSTM_LOOKBACK = checkpoint.get("lookback", 14)
            _GLOBAL_LSTM_MODEL = model
        else:
            model = _GLOBAL_LSTM_MODEL
        
        LOOKBACK = _GLOBAL_LSTM_LOOKBACK
        
        forecast_norm = []
        window = list(normalized[-LOOKBACK:])
        
        with torch.no_grad():
            for _ in range(forecast_days):
                x_in = torch.tensor(window[-LOOKBACK:], dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
                next_val = model(x_in).item()
                # Clamp prediction to prevent autoregressive explosion
                next_val = max(-1.0, min(2.0, next_val))
                forecast_norm.append(next_val)
                window.append(next_val)
                
        forecast_prices = [p * price_range + price_min for p in forecast_norm]
        
        # Calibration of confidence interval based on historical daily volatility of this specific asset
        std_returns = np.std(np.diff(price_array)) if len(price_array) > 1 else price_range * 0.02
        uncertainty = [std_returns * 1.96 * (i ** 0.5) for i in range(1, forecast_days + 1)]
        
        return {
            "forecast_prices": [round(float(p), 8) for p in forecast_prices],
            "lower_bound":     [round(float(p - u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "upper_bound":     [round(float(p + u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "model_used":      "Pre-trained Global LSTM Forecaster"
        }
        
    except Exception as e:
        print(f"[LSTM Forecast Error] {e}")
        raise RuntimeError(f"LSTM Deep Learning forecast failed: {e}")


def run_prophet_forecast(
    prices: pd.Series,
    dates: pd.Series,
    forecast_days: int = 30
) -> dict | None:
    """
    Uses NeuralProphet instead of Prophet.
    NeuralProphet is pure PyTorch — no Stan/C++ dependency.
    pip install neuralprophet==0.9.0
    """
    try:
        import logging
        logging.getLogger("NP.forecaster").setLevel(logging.ERROR)
        logging.getLogger("NP.utils").setLevel(logging.ERROR)

        from neuralprophet import NeuralProphet

        df = pd.DataFrame({
            "ds": pd.to_datetime(dates).dt.tz_localize(None),
            "y":  prices.values.astype(float)
        }).dropna()

        if len(df) < 14:
            return None

        model = NeuralProphet(
            n_forecasts=forecast_days,
            n_lags=14,
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            epochs=50,           # keep fast
            batch_size=16,
            learning_rate=0.01,
            verbose=False,
        )

        # NeuralProphet requires a validation split
        train_df, val_df = model.split_df(df, freq="D", valid_p=0.2)
        model.fit(train_df, freq="D", validation_df=val_df, progress=False)

        future = model.make_future_dataframe(
            df, periods=forecast_days, n_historic_predictions=False
        )
        forecast_df = model.predict(future)

        # NeuralProphet output columns: yhat1..yhat7
        forecast_prices = []
        for i in range(1, forecast_days + 1):
            col = f"yhat{i}"
            if col in forecast_df.columns:
                val = forecast_df[col].dropna().iloc[-1]
                forecast_prices.append(float(val))

        if len(forecast_prices) < forecast_days:
            return None

        # Compute uncertainty from residuals on training data
        train_preds = model.predict(train_df)
        residuals = []
        for i in range(1, forecast_days + 1):
            col = f"yhat{i}"
            if col in train_preds.columns and "y" in train_preds.columns:
                diff = (train_preds["y"] - train_preds[col]).dropna()
                residuals.extend(diff.abs().tolist())

        spread = float(np.std(residuals)) if residuals else float(
            prices.std() * 0.05)
        spread_95 = spread * 1.96
        uncertainty = [spread_95 * (1 + i * 0.15) for i in range(forecast_days)]

        return {
            "forecast_prices": [round(p, 8) for p in forecast_prices],
            "lower_bound":     [round(p - u, 8)
                               for p, u in zip(forecast_prices, uncertainty)],
            "upper_bound":     [round(p + u, 8)
                               for p, u in zip(forecast_prices, uncertainty)],
            "model_used":      "NeuralProphet"
        }

    except Exception as e:
        print(f"NeuralProphet forecast failed: {e}")
        return None


def run_ensemble_forecast(
    prices: pd.Series,
    dates: pd.Series,
    forecast_days: int = 30
) -> dict:
    """
    Runs LSTM and Prophet, averages their forecasts.
    If Prophet unavailable, returns LSTM only.
    """
    lstm_result   = run_lstm_forecast(prices, forecast_days)
    prophet_result = run_prophet_forecast(prices, dates, forecast_days)
    
    if prophet_result is None:
        lstm_result["ensemble"] = False
        return lstm_result
    
    # Average the two forecasts
    ensemble_prices = [
        (l + p) / 2
        for l, p in zip(lstm_result["forecast_prices"],
                        prophet_result["forecast_prices"])
    ]
    # Take the wider confidence interval for safety
    lower = [min(l, p) for l, p in zip(lstm_result["lower_bound"],
                                         prophet_result["lower_bound"])]
    upper = [max(l, p) for l, p in zip(lstm_result["upper_bound"],
                                         prophet_result["upper_bound"])]
    
    return {
        "forecast_prices": [round(float(p), 8) for p in ensemble_prices],
        "lower_bound":     [round(float(p), 8) for p in lower],
        "upper_bound":     [round(float(p), 8) for p in upper],
        "model_used":      "LSTM+Prophet Ensemble",
        "lstm_forecast":   lstm_result["forecast_prices"],
        "prophet_forecast": prophet_result["forecast_prices"],
        "ensemble":        True
    }
