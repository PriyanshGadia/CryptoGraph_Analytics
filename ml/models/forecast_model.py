"""
LSTM + Prophet ensemble for 60-day lookback, 7-day forecast.
Called on-demand by the FastAPI forecast endpoint.
"""
import numpy as np
import pandas as pd
from typing import Optional

_GLOBAL_LSTM_MODEL = None
_GLOBAL_LSTM_LOOKBACK = 14
_GLOBAL_LSTM_RESIDUAL_STD = None

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
        import logging
        from pathlib import Path

        logger = logging.getLogger(__name__)

        class LSTMForecaster(nn.Module):
            def __init__(self, hidden_size=64, num_layers=2, dropout=0.1, output_steps=30):
                super().__init__()
                self.output_steps = output_steps
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
                    nn.Linear(32, output_steps) # Direct multi-step output
                )
            
            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :]).squeeze(0) # [output_steps]
                
        if _GLOBAL_LSTM_MODEL is None:
            ckpt_path = None
            env_artifact_path = os.environ.get("ARTIFACT_PATH")
            possible_paths = []
            if env_artifact_path:
                possible_paths.append(Path(env_artifact_path) / "best_lstm.pt")
                
            possible_paths.extend([
                Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts" / "best_lstm.pt",
                Path(__file__).resolve().parent / "best_lstm.pt",
                Path("ml/artifacts/best_lstm.pt"),
                Path("../ml/artifacts/best_lstm.pt")
            ])
            for p in possible_paths:
                if p.exists() and p.is_file():
                    ckpt_path = p
                    break
                    
            if ckpt_path is None:
                logger.error("Pre-trained LSTM model checkpoint not found.")
                return None
                
            checkpoint = torch.load(str(ckpt_path), map_location="cpu")
            model = LSTMForecaster()
            
            # Strict validation
            try:
                model.load_state_dict(checkpoint["model_state_dict"], strict=True)
            except RuntimeError as e:
                logger.error(f"LSTM Architecture mismatch. Please retrain for Seq2Seq: {e}")
                return None
                
            model.eval()
            
            _GLOBAL_LSTM_LOOKBACK = checkpoint.get("lookback", 14)
            _GLOBAL_LSTM_RESIDUAL_STD = checkpoint.get("residual_std", None)
            _GLOBAL_LSTM_MODEL = model
        else:
            model = _GLOBAL_LSTM_MODEL
        
        LOOKBACK = _GLOBAL_LSTM_LOOKBACK
        model.eval() # Use standard evaluation mode, no MC Dropout
        
        with torch.no_grad():
            window = list(normalized[-LOOKBACK:])
            x_in = torch.tensor(window, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
            forecast_norm = model(x_in).cpu().numpy()
            
            # Truncate or pad to exactly forecast_days
            if len(forecast_norm) > forecast_days:
                forecast_norm = forecast_norm[:forecast_days]
            elif len(forecast_norm) < forecast_days:
                forecast_norm = np.pad(forecast_norm, (0, forecast_days - len(forecast_norm)), mode='edge')
                
            forecast_norm = np.clip(forecast_norm, 0.0, 1.0)
            forecast_prices = forecast_norm * price_range + price_min
        
        # Calculate rigorous empirical uncertainty scaling
        returns = np.diff(price_array) / price_array[:-1] if len(price_array) > 1 else np.array([0.02])
        historical_volatility = np.std(returns)
        
        uncertainty = []
        for i in range(forecast_days):
            # Scale linearly with square root of time
            time_scaled_vol = historical_volatility * np.sqrt(i + 1)
            price_uncertainty = forecast_prices[i] * time_scaled_vol * 1.96 # 95% Confidence Interval
            uncertainty.append(price_uncertainty)
            
        return {
            "forecast_prices": [round(float(p), 8) for p in forecast_prices],
            "lower_bound":     [round(float(p - u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "upper_bound":     [round(float(p + u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "model_used":      "Direct Seq2Seq LSTM Forecaster"
        }
        
    except Exception as e:
        logger.exception(f"Failed to load or run LSTM checkpoint: {e}")
        return None


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
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning)

        df = pd.DataFrame({
            "ds": pd.to_datetime(dates).dt.tz_localize(None),
            "y":  prices.values.astype(float)
        }).dropna()

        if len(df) < 14:
            return None

        # Dynamic epoch tuning based on data size (longer history = fewer epochs needed)
        dynamic_epochs = max(20, min(100, int(3000 / len(df)))) if len(df) > 0 else 50
        
        # Use built-in quantiles for probabilistic uncertainty
        model = NeuralProphet(
            n_forecasts=forecast_days,
            n_lags=14,
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            epochs=dynamic_epochs,
            batch_size=16,
            learning_rate=0.01,
            quantiles=[0.05, 0.95], # 90% confidence interval
        )

        # NeuralProphet requires a validation split for early stopping
        train_df, val_df = model.split_df(df, freq="D", valid_p=0.2)
        
        # Fit with early stopping to prevent overfitting
        model.fit(train_df, freq="D", validation_df=val_df, early_stopping=True, progress=False)

        future = model.make_future_dataframe(
            df, periods=forecast_days, n_historic_predictions=False
        )
        forecast_df = model.predict(future)

        # NeuralProphet output columns for quantiles might vary, usually "yhat{i} {quantile}%"
        forecast_prices = []
        lower_bounds = []
        upper_bounds = []
        
        for i in range(1, forecast_days + 1):
            col_mean = f"yhat{i}"
            col_low = f"yhat{i} 5.0%"
            col_high = f"yhat{i} 95.0%"
            
            if col_mean in forecast_df.columns:
                val = forecast_df[col_mean].dropna().iloc[-1]
                forecast_prices.append(float(val))
                
                # Extract quantiles if available, else fallback to empirical std
                if col_low in forecast_df.columns and col_high in forecast_df.columns:
                    val_low = forecast_df[col_low].dropna().iloc[-1]
                    val_high = forecast_df[col_high].dropna().iloc[-1]
                    lower_bounds.append(float(val_low))
                    upper_bounds.append(float(val_high))
                else:
                    # Fallback if quantiles failed to generate
                    ewma_vol = prices.pct_change().dropna().std() * prices.iloc[-1] * 1.96 * ((i)**0.5)
                    lower_bounds.append(float(val - ewma_vol))
                    upper_bounds.append(float(val + ewma_vol))

        if len(forecast_prices) < forecast_days:
            return None

        return {
            "forecast_prices": [round(p, 8) for p in forecast_prices],
            "lower_bound":     [round(p, 8) for p in lower_bounds],
            "upper_bound":     [round(p, 8) for p in upper_bounds],
            "model_used":      "NeuralProphet (Quantile Regression)"
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"NeuralProphet forecast failed: {e}")
        return None


def run_mean_reversion_forecast(
    prices: pd.Series,
    forecast_days: int = 30
) -> dict:
    """
    Fallback baseline model: Mean Reversion.
    Proper formula: forecast = mean_price + (last_price - mean_price) * (decay ^ t)
    """
    try:
        last_price = prices.iloc[-1]
        mean_price = prices.mean()
        std_price = prices.std()
        
        forecast_prices = []
        current_price = last_price
        decay = 0.85 # Decay factor towards mean
        
        for i in range(forecast_days):
            # Correctly pull towards mean
            current_price = mean_price + (current_price - mean_price) * decay
            forecast_prices.append(current_price)
            
        uncertainty = [std_price * 1.96 * ((i + 1) ** 0.5) for i in range(forecast_days)]
        
        return {
            "forecast_prices": [round(float(p), 8) for p in forecast_prices],
            "lower_bound":     [round(float(p - u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "upper_bound":     [round(float(p + u), 8) for p, u in zip(forecast_prices, uncertainty)],
            "model_used":      "Mean Reversion Baseline"
        }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"CRITICAL: Mean Reversion fallback failed: {e}")
        
        # Absolute last resort fallback: flatline current price with widening uncertainty
        fallback_prices = [float(prices.iloc[-1])] * forecast_days
        fallback_uncert = [float(prices.iloc[-1]) * 0.05 * (i+1)**0.5 for i in range(forecast_days)]
        
        return {
            "forecast_prices": [round(p, 8) for p in fallback_prices],
            "lower_bound":     [round(p - u, 8) for p, u in zip(fallback_prices, fallback_uncert)],
            "upper_bound":     [round(p + u, 8) for p, u in zip(fallback_prices, fallback_uncert)],
            "model_used":      "Emergency Flatline Fallback"
        }


def run_ensemble_forecast(
    prices: pd.Series,
    dates: pd.Series,
    forecast_days: int = 30
) -> dict:
    """
    Runs LSTM and Prophet, and weights their forecasts using Inverse-Variance Weighting (a form of meta-learning).
    This mathematically suppresses the contribution of the model that exhibits higher uncertainty.
    """
    lstm_result   = run_lstm_forecast(prices, forecast_days)
    prophet_result = run_prophet_forecast(prices, dates, forecast_days)
    
    if lstm_result is None and prophet_result is None:
        return run_mean_reversion_forecast(prices, forecast_days)
        
    if lstm_result is None:
        prophet_result["ensemble"] = False
        return prophet_result
        
    if prophet_result is None:
        lstm_result["ensemble"] = False
        return lstm_result
    
    ensemble_prices = []
    ensemble_lower = []
    ensemble_upper = []
    
    # Calculate True Inverse-Variance Weighting
    for i in range(forecast_days):
        l_price = lstm_result["forecast_prices"][i]
        p_price = prophet_result["forecast_prices"][i]
        
        # Approximate variance from the 95% confidence intervals
        # Interval is roughly +/- 1.96 * sigma, so variance = (width / (2 * 1.96))^2
        l_var = ((lstm_result["upper_bound"][i] - lstm_result["lower_bound"][i]) / (2 * 1.96)) ** 2
        p_var = ((prophet_result["upper_bound"][i] - prophet_result["lower_bound"][i]) / (2 * 1.96)) ** 2
        
        # Prevent division by zero
        l_var = max(l_var, 1e-8)
        p_var = max(p_var, 1e-8)
        
        w_l = 1.0 / l_var
        w_p = 1.0 / p_var
        
        # Weighted mean
        weighted_price = (w_l * l_price + w_p * p_price) / (w_l + w_p)
        ensemble_prices.append(weighted_price)
        
        # Ensemble variance
        ens_var = 1.0 / (w_l + w_p)
        ens_std = ens_var ** 0.5
        
        # 95% confidence interval for ensemble
        ensemble_lower.append(weighted_price - 1.96 * ens_std)
        ensemble_upper.append(weighted_price + 1.96 * ens_std)
    
    return {
        "forecast_prices": [round(float(p), 8) for p in ensemble_prices],
        "lower_bound":     [round(float(p), 8) for p in ensemble_lower],
        "upper_bound":     [round(float(p), 8) for p in ensemble_upper],
        "model_used":      "Inverse-Variance Weighted Ensemble (LSTM+Prophet)",
        "lstm_forecast":   lstm_result["forecast_prices"],
        "prophet_forecast": prophet_result["forecast_prices"],
        "ensemble":        True
    }
