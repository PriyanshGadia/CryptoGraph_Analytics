"""
LSTM + Prophet ensemble for 60-day lookback, 7-day forecast.
Called on-demand by the FastAPI forecast endpoint.
"""
import numpy as np
import pandas as pd
from typing import Optional

def run_lstm_forecast(
    prices: pd.Series,  # 60 days of close prices, daily
    forecast_days: int = 30
) -> dict:
    """
    Runs a simple but effective LSTM forecast.
    Uses PyTorch — already installed in the ML environment.
    
    Returns dict with:
      forecast_prices: list of 7 predicted prices
      lower_bound:     list of 7 lower confidence prices (95%)
      upper_bound:     list of 7 upper confidence prices (95%)
      model_used:      "LSTM"
    """
    # Normalize prices
    price_array = prices.values.astype(np.float32)
    price_min   = price_array.min()
    price_max   = price_array.max()
    price_range = price_max - price_min
    if price_range == 0:
        price_range = 1.0
    normalized  = (price_array - price_min) / price_range
    
    try:
        import torch
        import torch.nn as nn
        
        # Hardware Optimizations for CPU Training Speed
        import os
        num_cores = os.cpu_count() or 4
        torch.set_num_threads(num_cores)
        if hasattr(torch.backends, 'mkldnn') and torch.backends.mkldnn.is_available():
            torch.backends.mkldnn.enabled = True
    except ModuleNotFoundError:
        # Fallback if torch is not installed in the FastAPI environment
        last_price = price_array[-1]
        trend = (price_array[-1] - price_array[-7]) / 7 if len(price_array) >= 7 else 0
        forecast = [last_price + trend * i for i in range(1, forecast_days + 1)]
        spread = np.std(np.diff(price_array)) * 2 if len(price_array) > 1 else price_range * 0.05
        return {
            "forecast_prices": [round(float(p), 6) for p in forecast],
            "lower_bound":     [round(float(p - spread), 6) for p in forecast],
            "upper_bound":     [round(float(p + spread), 6) for p in forecast],
            "model_used":      "naive_trend (torch missing)"
        }
    
    # Prepare sequences: lookback=14 days to predict next 1 day
    LOOKBACK = 14
    X, y = [], []
    for i in range(LOOKBACK, len(normalized)):
        X.append(normalized[i-LOOKBACK:i])
        y.append(normalized[i])
    
    if len(X) < 10:
        # Not enough data — return naive forecast
        last_price = price_array[-1]
        trend = (price_array[-1] - price_array[-7]) / 7
        forecast = [last_price + trend * i for i in range(1, forecast_days + 1)]
        spread = np.std(np.diff(price_array)) * 2
        return {
            "forecast_prices": [round(float(p), 6) for p in forecast],
            "lower_bound":     [round(float(p - spread), 6) for p in forecast],
            "upper_bound":     [round(float(p + spread), 6) for p in forecast],
            "model_used":      "naive_trend"
        }
    
    X_t = torch.from_numpy(np.array(X, dtype=np.float32)).unsqueeze(-1)
    y_t = torch.from_numpy(np.array(y, dtype=np.float32))
    
    # Define LSTM model
    class LSTMForecaster(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=1, hidden_size=64,
                num_layers=2, batch_first=True, dropout=0.1
            )
            self.fc = nn.Sequential(
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1)
            )
        
        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :]).squeeze(-1)
    
    model = LSTMForecaster()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()
    
    # Train for 150 epochs (fast on CPU for 60-day window)
    model.train()
    for epoch in range(150):
        optimizer.zero_grad()
        pred = model(X_t)
        loss = criterion(pred, y_t)
        loss.backward()
        optimizer.step()
    
    # Generate 7-day forecast iteratively
    model.eval()
    forecast_norm = []
    window = list(normalized[-LOOKBACK:])
    
    with torch.no_grad():
        for _ in range(forecast_days):
            x_in = torch.tensor(window[-LOOKBACK:],
                dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
            next_val = model(x_in).item()
            forecast_norm.append(next_val)
            window.append(next_val)
    
    # Denormalize
    forecast_prices = [p * price_range + price_min for p in forecast_norm]
    
    # Confidence intervals: use historical prediction error as spread
    residuals = []
    with torch.no_grad():
        preds_train = model(X_t).numpy()
    for i, p in enumerate(preds_train):
        actual = y[i] * price_range + price_min
        predicted = p * price_range + price_min
        residuals.append(abs(actual - predicted))
    
    spread_1sigma = np.std(residuals) if residuals else price_range * 0.02
    spread_95 = spread_1sigma * 1.96
    
    # Uncertainty grows with forecast horizon
    uncertainty = [spread_95 * (1 + i * 0.15) for i in range(forecast_days)]
    
    return {
        "forecast_prices": [round(float(p), 8) for p in forecast_prices],
        "lower_bound":     [round(float(p - u), 8) 
                           for p, u in zip(forecast_prices, uncertainty)],
        "upper_bound":     [round(float(p + u), 8) 
                           for p, u in zip(forecast_prices, uncertainty)],
        "model_used":      "LSTM-2layer-64hidden"
    }


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
