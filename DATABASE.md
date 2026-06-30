# Database Schema Specification

This document details the Supabase PostgreSQL database schema. The database stores asset metadata, historical pricing, sentiment tracking, model registers, mathematical feature configurations, and graph snapshots.

## 1. Entity-Relationship Diagram (ERD)

```text
  +----------------------+
  |        assets        |
  +----------------------+
  | PK | id              |<----------------------------------+
  |    | symbol (Unique) |                                   |
  |    | name            |                                   |
  |    | sector          |                                   |
  |    | market_cap_usd  |                                   |
  |    | created_at      |                                   |
  +----------------------+                                   |
             |                                               |
             +-----------------------+                       |
             |                       |                       |
             v                       v                       |
  +----------------------+  +----------------------+         |
  |        ohlcv         |  |      sentiment       |         |
  +----------------------+  +----------------------+         |
  | PK | id              |  | PK | id              |         |
  | FK | asset_id        |  | FK | asset_id        |         |
  | UK | asset_id, timestamp| UK | asset_id, timestamp|     |
  |    | open            |  |    | sentiment_score |         |
  |    | high            |  |    | news_volume     |         |
  |    | low             |  |    | fear_greed      |         |
  |    | close           |  |    | community_score |         |
  |    | volume          |  |    | public_interest |         |
  +----------------------+  |    | sentiment_roll_3|         |
                            |    | sentiment_momen |         |
                            |    | fear_greed_norm |         |
                            +----------------------+         |
                                                             |
             +-----------------------+                       |
             |                       |                       |
             v                       v                       |
  +----------------------+  +----------------------+         |
  |     predictions      |  |  technical_features  |         |
  +----------------------+  +----------------------+         |
  | PK | id              |  | PK | id              |         |
  | FK | asset_id        |  | FK | asset_id        |         |
  |    | timestamp       |  | UK | asset_id, timestamp|     |
  |    | predicted_at    |  |    | rsi_14          |         |
  |    | direction       |  |    | macd            |         |
  |    | confidence      |  |    | macd_signal     |         |
  |    | vol_regime      |  |    | atr_14          |         |
  |    | shap_values(JSB)|  |    | bb_width        |         |
  |    | model_version   |  |    | returns_1d      |         |
  +----------------------+  |    | returns_7d      |         |
                            |    | volatility_7d   |         |
                            +----------------------+         |
                                                             |
             +-----------------------+                       |
             |                                               |
             v                                               v (source_asset & target_asset)
  +------------------------+                        +------------------------+
  |    macro_indicators    |                        |    graph_snapshots     |
  +------------------------+                        +------------------------+
  | PK | id                |                        | PK | id                |
  | UK | timestamp         |                        | FK | source_asset      |
  |    | fed_rate          |                        | FK | target_asset      |
  |    | cpi               |                        |    | timestamp         |
  |    | inflation         |                        |    | weight            |
  |    | vix               |                        |    | edge_type         |
  |    | fed_rate_z        |                        +------------------------+
  |    | cpi_z             |
  |    | inflation_z       |
  |    | vix_z             |
  +------------------------+

  +----------------------+
  |    model_registry    |
  +----------------------+
  | PK | id              |
  | UK | version         |
  |    | wandb_run_id    |
  |    | metrics (JSONB) |
  |    | artifact_path   |
  |    | deployed_at     |
  +----------------------+
```

---

## 2. Table Definitions

### 2.1 Table: `assets`
Contains reference metadata for the assets modeled by the system.
- **SQL DDL**:
  ```sql
  CREATE TABLE assets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol         TEXT UNIQUE NOT NULL,
    name           TEXT,
    sector         TEXT,
    market_cap_usd NUMERIC,
    created_at     TIMESTAMPTZ DEFAULT NOW()
  );
  ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable anonymous read access for public dashboard; restrict write access to the backend service role.

### 2.2 Table: `ohlcv`
Historical 1-day candlestick price data.
- **SQL DDL**:
  ```sql
  CREATE TABLE ohlcv (
    id         BIGSERIAL PRIMARY KEY,
    asset_id   UUID REFERENCES assets(id) ON DELETE CASCADE,
    timestamp  TIMESTAMPTZ NOT NULL,
    open       NUMERIC,
    high       NUMERIC,
    low        NUMERIC,
    close      NUMERIC,
    volume     NUMERIC,
    UNIQUE(asset_id, timestamp)
  );
  CREATE INDEX idx_ohlcv_asset_time ON ohlcv(asset_id, timestamp);
  ALTER TABLE ohlcv ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.3 Table: `sentiment`
Daily metrics capturing social sentiment, fear/greed levels, and public attention trends.
- **SQL DDL**:
  ```sql
  CREATE TABLE sentiment (
    id                     BIGSERIAL PRIMARY KEY,
    asset_id               UUID REFERENCES assets(id) ON DELETE CASCADE,
    timestamp              TIMESTAMPTZ NOT NULL,
    sentiment_score        NUMERIC,
    news_volume            INTEGER DEFAULT 0,
    fear_greed             INTEGER,
    community_score        NUMERIC,
    public_interest        NUMERIC,
    sentiment_rolling_3d   NUMERIC,
    sentiment_momentum     NUMERIC,
    fear_greed_norm        NUMERIC,
    UNIQUE(asset_id, timestamp)
  );
  CREATE INDEX idx_sentiment_asset_time ON sentiment(asset_id, timestamp);
  ALTER TABLE sentiment ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.4 Table: `predictions`
ST-GCN model outputs for direction, confidence, volatility regimes, and explainability.
- **SQL DDL**:
  ```sql
  CREATE TABLE predictions (
    id                BIGSERIAL PRIMARY KEY,
    asset_id          UUID REFERENCES assets(id) ON DELETE CASCADE,
    timestamp         TIMESTAMPTZ NOT NULL,
    predicted_at      TIMESTAMPTZ DEFAULT NOW(),
    direction         TEXT, -- e.g., 'strong_up', 'up', 'neutral', 'down', 'strong_down'
    confidence        NUMERIC,
    volatility_regime TEXT, -- e.g., 'low', 'medium', 'high', 'extreme'
    shap_values       JSONB,
    model_version     TEXT
  );
  CREATE INDEX idx_predictions_asset_time ON predictions(asset_id, timestamp);
  ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.5 Table: `graph_snapshots`
Constructed edge relationships (correlations, sector ties, market-cap ratios) for network rendering.
- **SQL DDL**:
  ```sql
  CREATE TABLE graph_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL,
    source_asset UUID REFERENCES assets(id),
    target_asset UUID REFERENCES assets(id),
    weight       NUMERIC,
    edge_type    TEXT
  );
  CREATE INDEX idx_graph_snapshots_time ON graph_snapshots(timestamp);
  ALTER TABLE graph_snapshots ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.6 Table: `technical_features`
Calculated math indicators from raw OHLCV records used for model nodes.
- **SQL DDL**:
  ```sql
  CREATE TABLE technical_features (
    id            BIGSERIAL PRIMARY KEY,
    asset_id      UUID REFERENCES assets(id) ON DELETE CASCADE,
    timestamp     TIMESTAMPTZ NOT NULL,
    rsi_14        NUMERIC,
    macd          NUMERIC,
    macd_signal   NUMERIC,
    atr_14        NUMERIC,
    bb_width      NUMERIC,
    returns_1d    NUMERIC,
    returns_7d    NUMERIC,
    volatility_7d NUMERIC,
    UNIQUE(asset_id, timestamp)
  );
  CREATE INDEX idx_technical_asset_time ON technical_features(asset_id, timestamp);
  ALTER TABLE technical_features ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.7 Table: `macro_indicators`
Macroeconomic indicators collected globally, daily or resampled to daily.
- **SQL DDL**:
  ```sql
  CREATE TABLE macro_indicators (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL UNIQUE,
    fed_rate    NUMERIC,
    cpi         NUMERIC,
    inflation   NUMERIC,
    vix         NUMERIC,
    fed_rate_z  NUMERIC,
    cpi_z       NUMERIC,
    inflation_z NUMERIC,
    vix_z       NUMERIC
  );
  ALTER TABLE macro_indicators ENABLE ROW LEVEL SECURITY;
  ```
- **RLS Policy**: Enable read access; restrict write actions.

### 2.8 Table: `model_registry`
Audited run configurations, artifact hashes, and metrics validated via validation subsets.
- **SQL DDL**:
  ```sql
  CREATE TABLE model_registry (
    id            BIGSERIAL PRIMARY KEY,
    version       TEXT UNIQUE,
    wandb_run_id  TEXT,
    metrics       JSONB,
    artifact_path TEXT,
    deployed_at   TIMESTAMPTZ DEFAULT NOW()
  );
  ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY;
  ```
  ```
- **RLS Policy**: Enable read access; restrict write actions.

---

## 3. SQLite Local Deployment (Standard Production Setup)

For highly portable and reproducible local environments (including Windows, macOS, Linux, and Android Termux), the platform defaults to a local **SQLite** database (`cryptograph.db`).

### 3.1 SQLite WAL & Concurrency Optimizations
To support massive concurrent database writes (e.g. daily websocket feeds, technical features computation, and deep learning evaluations) without blocking query operations, the SQLite engine is initialized with the following PRAGMAs:
* **WAL Mode (Write-Ahead Logging)**: Enables concurrent reads while writing.
* **Synchronous = NORMAL**: Balances persistence safety with write performance.
* **Cache Size**: Set to `-64000` (allocates 64MB of memory cache for high-speed indexing).

### 3.2 Predictions Schema Update
The local predictions schema maps PostgreSQL features into SQLite formats, substituting `JSONB` with SQLite's native `JSON` string parsing, and utilizes an `attestation_hash` column for transparency mapping:
* `attestation_hash` (TEXT): Replaces `zk_snark_proof` to map execution attestations securely.

### 3.3 New Table: `forecasts`
Stores ensembled forecasting outputs (LSTM, Prophet) for UI caching to prevent blocking event loop worker threads.
- **SQLite DDL**:
  ```sql
  CREATE TABLE forecasts (
      id                INTEGER PRIMARY KEY AUTOINCREMENT,
      asset_id          VARCHAR NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
      timestamp         DATETIME NOT NULL,
      forecast_prices   TEXT NOT NULL, -- JSON array
      lower_bound       TEXT NOT NULL, -- JSON array
      upper_bound       TEXT NOT NULL, -- JSON array
      lstm_forecast     TEXT,          -- JSON array (optional)
      prophet_forecast  TEXT           -- JSON array (optional)
  );
  CREATE INDEX idx_forecasts_asset_time ON forecasts(asset_id, timestamp);
  ```
