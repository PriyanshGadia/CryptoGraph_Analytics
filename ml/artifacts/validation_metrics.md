# ST-GCN Validation & Backtest Performance Report

This document registers the audited validation performance and historical backtesting metrics for the deployed ST-GCN spatio-temporal graph convolutional forecasting model.

## 1. Classification Metrics (Model Predictor Calibration)

* **Macro-averaged F1 Score**: `0.2476`
* **Macro-averaged Precision**: `0.2491`
* **Macro-averaged Recall**: `0.2623`

### 1.1 Confusion Matrix

| Actual \ Predicted | Strong Down | Down | Neutral | Up | Strong Up |
|---------------------|-------------|------|---------|----|-----------|
| **Strong Down**     |   0         | 19   |  1      |  1 |  0        |
| **Down**            |   0         | 22   | 20      |  6 |  2        |
| **Neutral**         |   0         | 14   | 17      |  6 |  0        |
| **Up**              |   0         | 14   | 11      |  7 |  1        |
| **Strong Up**       |   0         |  3   |  1      |  0 |  1        |

---

## 2. Portfolio Backtesting & Sharpe Performance

The strategy was evaluated using historical daily OHLCV prices, allocating equal fractions of capital to assets with high-confidence buy signals (`confidence > 0.65`).

* **Starting Capital**: `$100,000.00`
* **Sharpe Ratio (Annualized)**: `-1.0496`
* **Sortino Ratio (Annualized)**: `0.0000`
* **Maximum Drawdown**: `-1.28%`
* **Win Rate (Daily)**: `33.33%`
* **Profit Factor**: `0.82`

> [!NOTE]
> Detailed equity curve visual is generated and saved as `ml/artifacts/backtest_results.png`.
