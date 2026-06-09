# API Specification

This document details the OpenAPI-style specification for the ST-GCN Crypto Forecasting API backend.

## Base URL
`http://localhost:8000` (Local) / Production API Domain

---

## Endpoint Index

1. [GET /health](#1-get-health)
2. [GET /api/assets](#2-get-apiassets)
3. [GET /api/predictions](#3-get-apipredictions)
4. [GET /api/predictions/{symbol}](#4-get-apipredictionssymbol)
5. [POST /api/inference/trigger](#5-post-apiinferencetrigger)
6. [POST /api/etl/trigger](#6-post-apietltrigger)
7. [GET /api/graph/latest](#7-get-apigraphlatest)
8. [GET /api/graph/history](#8-get-apigraphhistory)
9. [GET /api/risk](#9-get-apirisk)
10. [GET /api/explain/{symbol}](#10-get-apiexplainsymbol)

---

## Endpoints

### 1. GET /health
Retrieves the status and server-time of the FastAPI service.

- **Method**: `GET`
- **Path**: `/health`
- **Response Schema** (`200 OK`):
  ```json
  {
    "status": "ok",
    "timestamp": "2026-06-01T08:00:00Z"
  }
  ```
- **Error Codes**:
  - None expected under standard operations.

---

### 2. GET /api/assets
Returns metadata for all tracked crypto assets along with their latest pricing and predicted labels.

- **Method**: `GET`
- **Path**: `/api/assets`
- **Response Schema** (`200 OK`):
  ```json
  [
    {
      "id": "e89c66cb-b0ad-44b4-8457-41dbd15eb0db",
      "symbol": "BTC",
      "name": "Bitcoin",
      "sector": "layer1",
      "market_cap_usd": 1250000000000.0,
      "current_price": 68500.5,
      "price_change_24h_pct": 2.45,
      "predicted_direction": "up",
      "confidence": 0.78
    }
  ]
  ```
- **Error Codes**:
  - `500 Internal Server Error`: DB query failed.

---

### 3. GET /api/predictions
Returns the latest predicted state for all assets. Offers query filtering options.

- **Method**: `GET`
- **Path**: `/api/predictions`
- **Query Parameters**:
  - `limit` (integer, default: `50`): Max number of predictions.
  - `direction` (string, default: `all`, choices: `strong_up`, `up`, `neutral`, `down`, `strong_down`, `all`): Filter by direction.
  - `min_confidence` (float, default: `0.0`, range: `0.0` - `1.0`): Filter predictions by minimum model confidence.
- **Response Schema** (`200 OK`):
  ```json
  [
    {
      "symbol": "BTC",
      "direction": "up",
      "confidence": 0.78,
      "volatility_regime": "low",
      "predicted_at": "2026-06-01T08:00:00Z",
      "model_version": "v1.0.0"
    }
  ]
  ```
- **Error Codes**:
  - `422 Unprocessable Entity`: Input parameters failed schema validation rules.

---

### 4. GET /api/predictions/{symbol}
Retrieves historical predictions (up to 30 intervals) for a single asset to display trend graphs.

- **Method**: `GET`
- **Path**: `/api/predictions/{symbol}`
- **Path Parameters**:
  - `symbol` (string): The asset symbol (e.g., `BTC`).
- **Response Schema** (`200 OK`):
  ```json
  {
    "symbol": "BTC",
    "history": [
      {
        "timestamp": "2026-06-01T00:00:00Z",
        "direction": "up",
        "confidence": 0.78,
        "volatility_regime": "low",
        "predicted_at": "2026-06-01T00:05:00Z"
      }
    ]
  }
  ```
- **Error Codes**:
  - `404 Not Found`: Asset symbol not tracked or no history exists.

---

### 5. POST /api/inference/trigger
Triggers a fresh inference pipeline asynchronously as a background subprocess.

- **Method**: `POST`
- **Path**: `/api/inference/trigger`
- **Response Schema** (`202 Accepted`):
  ```json
  {
    "status": "triggered",
    "message": "Inference pipeline successfully triggered asynchronously."
  }
  ```
- **Error Codes**:
  - `503 Service Unavailable`: Subprocess already running.

---

### 6. POST /api/etl/trigger
Triggers a fresh ETL ingestion and feature recalculation cycle asynchronously.

- **Method**: `POST`
- **Path**: `/api/etl/trigger`
- **Response Schema** (`202 Accepted`):
  ```json
  {
    "status": "triggered",
    "message": "ETL pipeline successfully triggered asynchronously."
  }
  ```
- **Error Codes**:
  - `503 Service Unavailable`: ETL process already running.

---

### 7. GET /api/graph/latest
Returns the latest spatial network snapshot for interactive rendering.

- **Method**: `GET`
- **Path**: `/api/graph/latest`
- **Response Schema** (`200 OK`):
  ```json
  {
    "nodes": [
      {
        "id": "BTC",
        "symbol": "BTC",
        "sector": "layer1",
        "market_cap_usd": 1250000000000.0,
        "predicted_direction": "up",
        "confidence": 0.78
      }
    ],
    "edges": [
      {
        "source": "BTC",
        "target": "ETH",
        "weight": 0.82,
        "edge_type": "correlation"
      }
    ]
  }
  ```
- **Error Codes**:
  - `500 Internal Server Error`: Graph builder error or snapshot retrieval failure.

---

### 8. GET /api/graph/history
Returns aggregate network metrics and stats tracking structural changes over time.

- **Method**: `GET`
- **Path**: `/api/graph/history`
- **Query Parameters**:
  - `days` (integer, default: `7`): Number of historical days to inspect.
- **Response Schema** (`200 OK`):
  ```json
  [
    {
      "timestamp": "2026-06-01T00:00:00Z",
      "edge_count": 124,
      "density": 0.101,
      "top_central_nodes": ["BTC", "ETH", "SOL"]
    }
  ]
  ```
- **Error Codes**:
  - `400 Bad Request`: Query days out of range (> 90 days).

---

### 9. GET /api/risk
Computes composite portfolio and asset metrics representing systemic risk.

- **Method**: `GET`
- **Path**: `/api/risk`
- **Response Schema** (`200 OK`):
  ```json
  {
    "market_regime": "bull",
    "average_volatility": 0.045,
    "correlation_clusters": {
      "cluster_0": ["BTC", "ETH", "LTC"],
      "cluster_1": ["UNI", "AAVE", "CRV"]
    },
    "top_movers": [
      {
        "symbol": "SOL",
        "returns_1d": 0.082,
        "direction": "strong_up",
        "volatility": "high"
      }
    ],
    "risk_alerts": [
      {
        "type": "Fear & Greed extreme",
        "severity": "high",
        "message": "Market Fear & Greed index is at 15 (Extreme Fear)."
      }
    ],
    "drawdown_history": [
      {
        "timestamp": "2026-06-01T00:00:00Z",
        "drawdown": -0.054
      }
    ]
  }
  ```
- **Error Codes**:
  - `500 Internal Server Error`: Calculation failure.

---

### 10. GET /api/explain/{symbol}
Generates a plain-English explanation explaining the model's prediction using the local SHAP values via the Groq LLM client.

- **Method**: `GET`
- **Path**: `/api/explain/{symbol}`
- **Path Parameters**:
  - `symbol` (string): The target asset symbol (e.g., `BTC`).
- **Response Schema** (`200 OK`):
  ```json
  {
    "symbol": "BTC",
    "explanation": "The ST-GCN model predicts BTC will go up with 78.0% confidence over the next 24 hours. This forecast is heavily supported by a strong positive 1-day return and positive social sentiment. Elevated VIX levels marginally reduced confidence, but the positive sector correlations remain dominant.",
    "direction": "up",
    "confidence": 0.78,
    "top_features": {
      "returns_1d": 0.12,
      "sentiment_score": 0.08,
      "vix_z": -0.03,
      "rsi_14": 0.02
    }
  }
  ```
- **Error Codes**:
  - `404 Not Found`: Asset symbol has no active SHAP features or predictions.
  - `502 Bad Gateway`: Groq API communication failure.
