import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi_exact(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Convert to numpy for fast loop
    gain_arr = gain.values
    loss_arr = loss.values
    
    avg_gain = np.zeros_like(gain_arr)
    avg_loss = np.zeros_like(loss_arr)

    # First value is simple moving average
    avg_gain[period] = np.nanmean(gain_arr[1:period+1])
    avg_loss[period] = np.nanmean(loss_arr[1:period+1])

    # Wilder's Smoothing
    for i in range(period + 1, len(series)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gain_arr[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + loss_arr[i]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    rsi[:period] = np.nan
    return pd.Series(rsi, index=series.index)

btc = yf.Ticker("BTC-USD").history(period="1y")
print("Exact BTC RSI:", calculate_rsi_exact(btc['Close'], 14).iloc[-1])
