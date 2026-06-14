import yfinance as yf
import pandas as pd

def calculate_rsi_wilder(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# Fetch live BTC and ETH data
btc = yf.Ticker("BTC-USD").history(period="3mo")
eth = yf.Ticker("ETH-USD").history(period="3mo")

print("--- RSI VERIFICATION ---")
print(f"BTC Latest Close: {btc['Close'].iloc[-1]}")
print(f"BTC RSI (14)    : {calculate_rsi_wilder(btc['Close'], 14).iloc[-1]:.2f}")
print(f"ETH Latest Close: {eth['Close'].iloc[-1]}")
print(f"ETH RSI (14)    : {calculate_rsi_wilder(eth['Close'], 14).iloc[-1]:.2f}")
