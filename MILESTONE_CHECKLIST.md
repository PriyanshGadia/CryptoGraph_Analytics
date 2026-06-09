# Milestone Implementation Checklist

This checklist tracks the implementation of the ST-GCN Financial Forecasting Platform across all development phases. Each milestone details the target files to create, the commands to execute for verification, and the expected outputs.

---

## Phase 0: Architecture & Design (Current)

- [x] Create core architectural specification documents.
  - **Files Created**:
    - [ARCHITECTURE.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/ARCHITECTURE.md)
    - [DATABASE.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/DATABASE.md)
    - [API_SPEC.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/API_SPEC.md)
    - [MODEL_SPEC.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/MODEL_SPEC.md)
    - [DEPLOYMENT.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/DEPLOYMENT.md)
    - [MILESTONE_CHECKLIST.md](file:///Users/akhsatjain/Desktop/Crypto_Graph_Analysis/MILESTONE_CHECKLIST.md) (This file)
  - **Verification Command**: None (Architectural review).
  - **Expected Output**: Successful parsing and alignment on design guidelines.

---

## Phase 1: Database Schema & Infrastructure

- [ ] Create Supabase SQL migration files and apply schemas.
  - **Files Created**:
    - `database/migrations/001_create_assets.sql`
    - `database/migrations/002_create_ohlcv.sql`
    - `database/migrations/003_create_sentiment.sql`
    - `database/migrations/004_create_predictions.sql`
    - `database/migrations/005_create_graph_snapshots.sql`
    - `database/migrations/006_create_feature_store.sql`
  - **Verification Command**: Apply migration files via Supabase dashboard or CLI:
    ```bash
    supabase db push --linked
    ```
  - **Expected Output**: All 8 tables successfully provisioned in the Supabase schema with RLS active and foreign key constraints verified.

---

## Phase 2: Data Collection Ingestions

- [ ] Implement data ingestion collectors.
  - **Files Created**:
    - `ml/data/ingestion/binance_collector.py`
    - `ml/data/ingestion/fred_collector.py`
    - `ml/data/ingestion/sentiment_collector.py`
    - `ml/data/ingestion/fear_greed_collector.py`
  - **Verification Command**: Execute collectors manually for verification:
    ```bash
    python ml/data/ingestion/binance_collector.py
    python ml/data/ingestion/fred_collector.py
    python ml/data/ingestion/sentiment_collector.py
    python ml/data/ingestion/fear_greed_collector.py
    ```
  - **Expected Output**: Console outputs:
    - `"Collected BTC: X rows"`
    - `"Collected sentiment for BTC"`
    - `"Collected X fear & greed data points"`
    - Verify Supabase tables (`ohlcv`, `sentiment`, `macro_indicators`) are populated with entries.

---

## Phase 3: Feature Engineering & Feature Store

- [ ] Develop indicators computation and feature validation module.
  - **Files Created**:
    - `ml/data/feature_engineering/technical_indicators.py`
    - `ml/data/feature_engineering/sentiment_features.py`
    - `ml/data/feature_engineering/macro_features.py`
    - `ml/data/feature_store/store.py`
    - `ml/data/feature_store/validator.py`
  - **Verification Command**: Run feature computations and verification validation scripts:
    ```bash
    python ml/data/feature_engineering/technical_indicators.py
    python ml/data/feature_engineering/sentiment_features.py
    python ml/data/feature_engineering/macro_features.py
    python ml/data/feature_store/validator.py
    ```
  - **Expected Output**:
    - Console output: `"Computed features for BTC: X rows"`
    - Validator status prints: `"Validation success: All checks passed. Row Count: X, NaN Count: 0, Bounds Valid."`

---

## Phase 4: Graph Construction

- [ ] Develop the dynamic spatio-temporal graph builder.
  - **Files Created**:
    - `ml/graph/edge_types.py`
    - `ml/graph/graph_builder.py`
    - `ml/graph/dynamic_graph.py`
  - **Verification Command**: Execute the graph snapshot builder for a test interval:
    ```bash
    python -c "from ml.graph.graph_builder import test_builder; test_builder()"
    ```
  - **Expected Output**:
    - Node matrix shape matches `(50, 24)`.
    - Edge list contains connections (> 0.6 correlation, sector matches, market-cap ratios).
    - Summary analytics output: `"Graph Density: X, Central Nodes: [...]"`

---

## Phase 5: GNN Model Architecture

- [ ] Implement the PyTorch Geometric ST-GCN network layers.
  - **Files Created**:
    - `ml/models/gat_temporal.py`
    - `ml/models/temporal_transformer.py`
    - `ml/models/heads.py`
    - `ml/models/stgcn.py`
  - **Verification Command**: Run forward check passes using a simulated tensor block:
    ```bash
    python -c "from ml.models.stgcn import test_forward_pass; test_forward_pass()"
    ```
  - **Expected Output**: Forward pass completes without error. Logged outputs:
    - `"Direction Logits Shape: torch.Size([50, 5])"`
    - `"Volatility Logits Shape: torch.Size([50, 4])"`

---

## Phase 6: Training Pipeline & Loss

- [ ] Build the training loop, loss metrics, and callbacks.
  - **Files Created**:
    - `ml/training/loss.py`
    - `ml/training/metrics.py`
    - `ml/training/callbacks.py`
    - `ml/training/trainer.py`
  - **Verification Command**: Run a short 2-epoch model fitting process on a dummy graph sequence:
    ```bash
    python -c "from ml.training.trainer import run_dummy_training; run_dummy_training()"
    ```
  - **Expected Output**:
    - Trainer prints epoch metrics.
    - Loss decreases between Epoch 1 and Epoch 2.
    - Early stopping and ModelCheckpoint modules save a test artifact `best_model.pt`.

---

## Phase 7: Evaluation & Model Explainability

- [ ] Implement backtesting engine and SHAP feature importance extraction.
  - **Files Created**:
    - `ml/evaluation/finance_metrics.py`
    - `ml/evaluation/backtester.py`
    - `ml/evaluation/explainability.py`
  - **Verification Command**: Run evaluation check on local saved model:
    ```bash
    python ml/evaluation/backtester.py --test-run
    python ml/evaluation/explainability.py --test-run
    ```
  - **Expected Output**:
    - Equity curve outputs generated: `ml/artifacts/backtest_results.png`
    - Top SHAP features saved: `ml/artifacts/shap_summary.png`
    - Predictions table updated with SHAP JSON output strings.

---

## Phase 8: Automation Pipelines

- [ ] Package ML workflows into structured pipeline execution files.
  - **Files Created**:
    - `ml/pipelines/etl_pipeline.py`
    - `ml/pipelines/training_pipeline.py`
    - `ml/pipelines/inference_pipeline.py`
    - `ml/experiments/wandb_tracker.py`
    - `ml/hyperopt/optuna_search.py`
  - **Verification Command**: Execute the full ETL pipeline script:
    ```bash
    python ml/pipelines/etl_pipeline.py
    ```
  - **Expected Output**:
    - Successful feature validation.
    - Prints: `"ETL Pipeline completed successfully"`.

---

## Phase 9: FastAPI Backend REST API

- [ ] Develop backend routes, database clients, and config settings.
  - **Files Created**:
    - `backend/app/main.py`
    - `backend/app/core/config.py`
    - `backend/app/core/security.py`
    - `backend/app/db/supabase_client.py`
    - `backend/app/db/models.py`
    - `backend/app/api/deps.py`
    - `backend/app/api/routes/assets.py`
    - `backend/app/api/routes/predictions.py`
    - `backend/app/api/routes/graph.py`
    - `backend/app/api/routes/risk.py`
    - `backend/app/api/routes/explain.py`
  - **Verification Command**: Launch FastAPI local server and query endpoint:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    curl -f http://localhost:8000/health
    ```
  - **Expected Output**:
    - Console outputs: `"Application startup complete."`
    - Health check returns `{"status": "ok"}`.

---

## Phase 10: Next.js Frontend Dashboard

- [ ] Implement Next.js dashboard pages and user interface components.
  - **Files Created**:
    - `frontend/app/layout.tsx`
    - `frontend/app/page.tsx`
    - `frontend/app/market/page.tsx`
    - `frontend/app/graph/page.tsx`
    - `frontend/app/predictions/page.tsx`
    - `frontend/app/risk/page.tsx`
    - `frontend/app/explain/page.tsx`
    - `frontend/components/GraphNetwork.tsx`
    - `frontend/components/PredictionCard.tsx`
    - `frontend/components/RiskPanel.tsx`
    - `frontend/components/ExplainPanel.tsx`
    - `frontend/components/MarketOverview.tsx`
    - `frontend/lib/api.ts`
    - `frontend/lib/supabase.ts`
  - **Verification Command**: Start local Next.js client and verify build:
    ```bash
    npm run build
    npm run dev
    ```
  - **Expected Output**:
    - Node CLI reports: `"Ready in Xms"`
    - Browser opens `http://localhost:3000` with active rendering of components.

---

## Phase 11: Deployment & CI/CD Configurations

- [ ] Finalize Docker and GitHub actions deployment descriptors.
  - **Files Created**:
    - `docker-compose.yml`
    - `backend/Dockerfile`
    - `ml/Dockerfile`
    - `frontend/Dockerfile`
    - `.github/workflows/ci.yml`
    - `.github/workflows/deploy.yml`
    - `Makefile`
    - `README.md`
  - **Verification Command**: Build local Docker stack:
    ```bash
    docker-compose up --build -d
    ```
  - **Expected Output**:
    - Docker daemon reports all container runs active.
    - Public requests to port 3000 display the frontend connected to port 8000.
