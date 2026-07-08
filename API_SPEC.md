# API Specification

This document provides a detailed specification of the **CryptoGraph Analytics FastAPI** backend endpoints, request payloads, response structures, and WebSocket communication protocols.

All API routes (unless otherwise specified) are exposed under the `/api/v1` prefix and require header-based authentication.

---

## 🔒 Authentication

All REST endpoints under `/api/v1` are protected by a security dependency. You must include the following header in your requests:

| Header | Type | Description |
| :--- | :--- | :--- |
| `X-API-Key` | `string` | Cryptographically strong API key defined in the backend environment variables. |

For WebSocket connections, since headers cannot easily be set during native browser handshakes, the API key must be provided as a query parameter:
`ws://localhost:8000/api/v1/stream/market?api_key=YOUR_API_KEY`

---

## 📋 Endpoint Index

> [!NOTE]
> All paths below are absolute, but in the actual codebase they are prefixed with `/api/v1` except for `/health`.

| Category | Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- | :--- |
| **System** | `GET` | `/health` | No | System health check (DB connectivity & server timestamp) |
| **System** | `GET` | `/api/v1/status` | Yes | High-level system summaries and metrics |
| **System** | `POST` | `/api/v1/status/refresh-all` | Yes | Triggers a full data-ingestion and feature recalculation cycle |
| **System** | `GET` | `/api/v1/status/performance/model_health` | Yes | Returns active ML model performance metrics |
| **Assets** | `GET` | `/api/v1/assets` | Yes | Lists all tracked assets with latest SSOT prices & prediction labels |
| **Coins** | `GET` | `/api/v1/coins/{symbol}/ohlcv` | Yes | Retrieves historical daily close OHLCV candles |
| **Coins** | `GET` | `/api/v1/coins/{symbol}/indicators` | Yes | Retrieves technical indicator history (RSI, MACD, volatility) |
| **Coins** | `GET` | `/api/v1/coins/{symbol}/prediction-history` | Yes | Retrieves single-coin prediction registers |
| **Coins** | `GET` | `/api/v1/coins/{symbol}/correlations` | Yes | Retrieves close-price correlations against other tracked assets |
| **Coins** | `GET` | `/api/v1/coins/{symbol}/sentiment-history` | Yes | Retrieves qualitative and synthetic sentiment history |
| **Predictions** | `GET` | `/api/v1/predictions` | Yes | Lists recent prediction registers (direction, confidence, volatility) |
| **Predictions** | `POST` | `/api/v1/predictions/batch` | Yes | Submits a batch query of predictions for multiple assets |
| **Predictions** | `GET` | `/api/v1/predictions/validation-metrics` | Yes | Retrieves chronological F1 validation scores and Sharpe thresholds |
| **Predictions** | `GET` | `/api/v1/predictions/{symbol}` | Yes | Retrieves historical predictions for a single coin |
| **Predictions** | `POST` | `/api/v1/predictions/inference/trigger` | Yes | Manually forces a model forward pass |
| **Explain** | `GET` | `/api/v1/explain/{symbol}` | Yes | Fetches LLaMA 3.3 plain-English prediction reasons |
| **Forecast** | `GET` | `/api/v1/forecast/{symbol}` | Yes | Fetches 7-day ensembled price predictions (LSTM & NeuralProphet) |
| **Graph** | `GET` | `/api/v1/graph/latest` | Yes | Fetches topological correlation matrix nodes/edges for visualization |
| **Correlations**| `GET` | `/api/v1/correlations/matrix` | Yes | Fetches a 2D float array of returns correlation |
| **Correlations**| `GET` | `/api/v1/correlations/sector-average` | Yes | Fetches sector-average correlation values |
| **Screener** | `GET` | `/api/v1/screener` | Yes | Returns filtered list of assets based on custom query params |
| **Screener** | `GET` | `/api/v1/screener/presets/{preset_name}`| Yes | Returns assets satisfying a preset filter |
| **Screener** | `POST` | `/api/v1/screener/refresh` | Yes | Manually forces live technical indicator updates |
| **Sentiment** | `GET` | `/api/v1/sentiment-data/fear-greed-history`| Yes | Returns Alternative.me Fear & Greed index history |
| **Sentiment** | `GET` | `/api/v1/sentiment-data/fear-greed-vs-btc`| Yes | Combined dataset for dual-axis charting (F&G vs. BTC) |
| **Sentiment** | `GET` | `/api/v1/sentiment-data/latest-synthesis` | Yes | Returns MoA Swarm macro qualitative text |
| **Portfolio** | `GET` | `/api/v1/portfolio` | Yes | Returns simulated paper-trading statistics and holdings |
| **Portfolio** | `POST` | `/api/v1/portfolio/execute` | Yes | Places a simulated paper trade order |
| **Portfolio** | `POST` | `/api/v1/portfolio/reset` | Yes | Wipes paper trading balance and resets to baseline |
| **Scheduler** | `GET` | `/api/v1/scheduler/status` | Yes | Gets active background scheduler running states |
| **Backtest** | `POST` | `/api/v1/backtest` | Yes | Evaluates backtested algorithms on historical records |
| **WebSockets** | `WS` | `/api/v1/stream/ticker/{symbol}`| Yes* | Streams live pricing ticker updates for a single asset |
| **WebSockets** | `WS` | `/api/v1/stream/market` | Yes* | Streams live tickers for all active assets |
| **WebSockets** | `WS` | `/api/v1/stream/predictions` | Yes* | Streams live prediction state updates |
| **WebSockets** | `WS` | `/api/v1/stream/screener` | Yes* | Streams live screener technical indicator metrics |

---

## 🛰️ Core Endpoint Details

### 1. General System Health
* **Endpoint:** `GET /health`
* **Response `200 OK`:**
  ```json
  {
    "status": "ok",
    "db": "healthy",
    "timestamp": "2026-07-08T15:32:17.194Z"
  }
  ```

### 2. Assets (SSOT Catalog)
* **Endpoint:** `GET /api/v1/assets`
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "e2fcd34d-8b01-44bb-ac21-d762f010b9f0",
      "symbol": "BTC",
      "name": "Bitcoin",
      "sector": "Layer 1",
      "market_cap_usd": 1285000000.0,
      "current_price": 93250.4,
      "price_change_24h_pct": 1.45,
      "predicted_direction": "up",
      "confidence": 0.85,
      "confidence_interval": [0.81, 0.89],
      "updated_at": "2026-07-08T15:30:00Z"
    }
  ]
  ```

### 3. Forecasting Endpoint
* **Endpoint:** `GET /api/v1/forecast/{symbol}`
* **Response `200 OK`:**
  ```json
  {
    "symbol": "BTC",
    "current_price": 93250.4,
    "forecast_days": 30,
    "prices": [93410.2, 93620.5, 93800.1],
    "lower_bound": [92100.0, 91500.5, 90800.2],
    "upper_bound": [94700.5, 95800.0, 96900.5],
    "lstm_raw": [93450.0, 93600.0, 93750.0],
    "prophet_raw": [93370.4, 93641.0, 93850.2]
  }
  ```

### 4. Correlation Graph
* **Endpoint:** `GET /api/v1/graph/latest`
* **Response `200 OK`:**
  ```json
  {
    "nodes": [
      { "id": "BTC", "group": "Layer 1", "size": 1.5, "price": 93250.4 },
      { "id": "ETH", "group": "Smart Contracts", "size": 1.2, "price": 3120.5 }
    ],
    "links": [
      { "source": "BTC", "target": "ETH", "value": 0.82, "type": "correlation" }
    ]
  }
  ```

### 5. AI Explainability
* **Endpoint:** `GET /api/v1/explain/{symbol}`
* **Response `200 OK`:**
  ```json
  {
    "symbol": "BTC",
    "direction": "up",
    "confidence": 0.85,
    "explanation": "Bitcoin exhibits strong accumulation trends above key moving averages, coupled with decreasing VIX volatility and bullish sentiment indices.",
    "attribution_weights": {
      "rsi_14": 0.35,
      "returns_7d": 0.25,
      "fed_rate": -0.15,
      "fear_greed": 0.10,
      "st_gcn_network": 0.15
    },
    "model_version": "1.0.0-Ensemble"
  }
  ```

### 6. Executing Simulated Paper Trade
* **Endpoint:** `POST /api/v1/portfolio/execute`
* **Request Payload:**
  ```json
  {
    "symbol": "BTC",
    "action": "BUY",
    "amount": 0.05
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "status": "executed",
    "trade_id": "tr_9a87d0912f",
    "symbol": "BTC",
    "action": "BUY",
    "executed_price": 93250.4,
    "cost": 4662.52,
    "remaining_balance": 95337.48
  }
  ```

---

## 📡 WebSocket API

The system provides multiple high-performance WebSockets paths under `/api/v1/stream/*`. 

### Connection Sequence
1. The client connects with the API key in the query parameter (e.g. `?api_key=dev_default_secure_key_...`).
2. The server accepts and maintains the frame subscription.
3. Live JSON messages are piped to the client on every ticker/tick event or background calculation.

### Stream Payloads Example

#### `ws://localhost:8000/api/v1/stream/ticker/{symbol}`
Sends tick-by-tick real-time price updates for a singular currency asset.
```json
{
  "symbol": "DYDX",
  "price": 0.12562,
  "high_24h": 0.13400,
  "low_24h": 0.12100,
  "volume_24h": 4120500.0,
  "timestamp": 1783437053723
}
```

#### `ws://localhost:8000/api/v1/stream/predictions`
Broadcasts updated prediction vectors universe-wide when background tasks compute new model snapshots.
```json
{
  "timestamp": "2026-07-08T15:30:00Z",
  "predictions": {
    "BTC": { "direction": "up", "confidence": 0.85 },
    "ETH": { "direction": "neutral", "confidence": 0.50 }
  }
}
```
