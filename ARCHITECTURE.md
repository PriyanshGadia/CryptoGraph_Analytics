# Architecture Specification

This document details the system design, component mapping, data flow, and technology choices for the ST-GCN Financial Forecasting Platform.

## 1. System Diagram

Below is the high-level architecture diagram illustrating the integration between the external data sources, the ML pipeline, the storage layer, the API backend, and the interactive frontend.

```text
+---------------------------------------------------------------------------------+
|                               EXTERNAL DATA SOURCES                             |
|                                                                                 |
|  +-------------------+       +--------------------+      +-------------------+  |
|  | Binance API (USDT) |       | FRED Macro API     |      | CoinGecko API     |  |
|  +---------+---------+       +---------+----------+      +---------+---------+  |
|            |                           |                           |            |
+------------|---------------------------|---------------------------|------------+
             |                           |                           |
             v                           v                           v
+------------|---------------------------|---------------------------|------------+
|            |                           |                           |            |
|            +-----------------------+   |   +-----------------------+            |
|                                    |   |   |                                    |
|                                    v   v   v                                    |
|                            +-----------+-----------+                            |
|                            |   ETL Pipeline (ML)   |                            |
|                            +-----------+-----------+                            |
|                                        |                                        |
|                                        v                                        |
|                            +-----------+-----------+                            |
|                            |     Feature Store     |                            |
|                            +-----------+-----------+                            |
|                                        |                                        |
|                                        v                                        |
|                            +-----------+-----------+                            |
|                            |  Dynamic Graph Builder|                            |
|                            +-----------+-----------+                            |
|                                        |                                        |
|                                        v                                        |
|                            +-----------+-----------+                            |
|                            |   ST-GCN Deep Model   |                            |
|                            +-----------+-----------+                            |
|                                        |                                        |
|                                        v                                        |
|                            +-----------+-----------+                            |
|                            |  Explainability (SHAP)|                            |
|                            +-----------+-----------+                            |
|                                        |                                        |
|                                        | (Upsert Predictions & Features)        |
|                                        v                                        |
|  +-------------------------------------+-------------------------------------+  |
|  |                                 DATABASE                                  |  |
|  |                                                                           |  |
|  |                         +-----------------------+                         |  |
|  |                         |   Supabase Database   |                         |  |
|  |                         +-----------+-----------+                         |  |
|  +-------------------------------------|-------------------------------------+  |
|                                        |                                        |
|                                        | (Read / Query via Service Role)        |
|                                        v                                        |
|  +-------------------------------------+-------------------------------------+  |
|  |                                 BACKEND API                               |  |
|  |                                                                           |  |
|  |                         +-----------------------+                         |  |
|  |                         |   FastAPI Application |                         |  |
|  |                         +-----------+-----------+                         |  |
|  |                                     |                                     |  |
|  |                                     v (LangChain / Groq API Calls)        |  |
|  |                         +-----------+-----------+                         |  |
|  |                         |      Groq Cloud       |                         |  |
|  |                         | (Llama 3.3 70B Model) |                         |  |
|  |                         +-----------------------+                         |  |
|  +-------------------------------------|-------------------------------------+  |
|                                        |                                        |
|                                        | (JSON REST API Response)               |
|                                        v                                        |
|  +-------------------------------------+-------------------------------------+  |
|  |                                  FRONTEND                                 |  |
|  |                                                                           |  |
|  |                       +---------------------------+                       |  |
|  |                       |  Next.js 14 Dashboard App  |                       |  |
|  |                       +---------------------------+                       |  |
|  +---------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------+
```

---

## 2. Service Map

The microservice topography describes the boundaries and interactions between distinct runtime units:

```text
                     +---------------------------------------+
                     |         Frontend (Next.js 14)         |
                     |  Host: Vercel                         |
                     +-------+-----------------------+-------+
                             |                       |
            (Fetch REST API) |                       | (Direct Read / Auth)
                             v                       v
        +--------------------+----+      +-----------+-----------+
        |     Backend (FastAPI)    |      |  Supabase Auth / DB   |
        |  Host: Render Web Service|      |  (PostgreSQL + RLS)   |
        +------------+-------------+      +-----------+-----------+
                     |                                ^
         (Query DB)  |                                | (Write snapshot/predict)
                     v                                |
     +---------------+---------------+                |
     |         Supabase DB           |                |
     |   Service Role Connection     |                |
     +-------------------------------+                |
                                                      |
                                                      |
                                           +----------+----------+
                                           |     ML Worker       |
                                           | Host: Render Worker |
                                           | Run: ETL / Training |
                                           +----------+----------+
                                                      |
                                                      v (API Calls)
                                           +----------+----------+
                                           |    External APIs    |
                                           |  (Binance / FRED /  |
                                           |     CoinGecko)      |
                                           +---------------------+
```

- **Frontend (Next.js 14)**: Served via Vercel. Communicates with Backend REST API for analytical predictions and graph states, and initializes Supabase client via `supabase-js` using the anon key.
- **Backend API (FastAPI)**: Runs as a Dockerized web service on Render. Interacts directly with the Supabase PostgreSQL database using the `SUPABASE_SERVICE_ROLE_KEY` to retrieve predictions, graph structures, and historical OHLCV data. Talks to the external **Groq LLM** to generate natural-language explanations.
- **ML Worker**: Runs as a background processing instance on Render. Spun up daily via cron (or manually triggered) to run the pipeline tasks: data ingestion, feature computation, model prediction, and database writes.
- **Supabase DB**: PostgreSQL database acting as the unified storage tier for RAW data, engineered features, model evaluations, model registry records, and predictions.

---

## 3. Data Flow

The flow of data through the system is structured as a linear sequence of transformations:

1. **Ingestion Layer**:
   - `binance_collector.py` collects OHLCV candles daily.
   - `fred_collector.py` collects macroeconomic indicators.
   - `sentiment_collector.py` collects social/community metrics from CoinGecko.
   - `fear_greed_collector.py` collects market fear-and-greed indexes.
   - *Result*: Upserted into Supabase tables `ohlcv`, `macro_indicators`, and `sentiment`.

2. **Feature Store**:
   - `store.py` reads raw data from Supabase, synchronizes dates, handles missing indices, and applies standard feature transforms (MACD, RSI, etc.).
   - `validator.py` ensures strict boundary checks (no NaN values, correct intervals).

3. **Graph Construction**:
   - `graph_builder.py` constructs a daily spatial graph. It correlates prices (using 30-day Pearson indices), maps sector classifications, and evaluates market-cap proportions to construct static/dynamic multi-relational edges.

4. **Model Forward Pass (Inference/Training)**:
   - For a sequence of 30 timesteps, node features are projected to size 128.
   - Graph features are processed through GATv2 layers to compute spatial representations.
   - Spatially augmented sequences are compiled along the temporal axis via a Positional Temporal Transformer.
   - Predictions are computed by the Multi-Task classifier heads.

5. **Predictions & Explanation**:
   - Predictions are generated for Market Direction (5 classes) and Volatility Regime (4 classes).
   - `explainability.py` extracts the local SHAP values representing feature importances.
   - Predictions and SHAP inputs are upserted into the `predictions` table in Supabase.

6. **API Retrieval & Visualization**:
   - The FastAPI backend queries the latest predicted state.
   - If explainability is queried, it feeds predictions and SHAP weights to the **Groq API** to construct plain-English analytical text.
   - Next.js fetches structured data and plots visualizations (Recharts, react-force-graph-2d).

---

## 4. Technology Decisions Rationale

| Technology | Selected Stack | Rationale |
| :--- | :--- | :--- |
| **LLM Inference** | **Groq Cloud (llama-3.3-70b-versatile)** | Ultra-low latency inference engine. Utilizing LangChain integrations (`langchain-groq`), this configuration provides structured token generation for explanations without the performance bottlenecks of slower API providers. |
| **Sentiment Data** | **CoinGecko Free API + Fear & Greed API** | Public, zero-cost data sources providing robust community indicators, public interest, and fear/greed metrics. Avoids complex OAuth credentials and rate-limiting payloads associated with Twitter/Reddit scraping. |
| **Database** | **Supabase (PostgreSQL)** | Combines SQL relational integrity with instant API layers. Built-in Row Level Security (RLS) protects data tables, while indexing capability handles high-volume Spatio-Temporal snapshots. |
| **ML Framework** | **PyTorch + PyTorch Geometric** | Standard-setting library for Graph Neural Networks. PyG's dynamic graph implementations and optimized CUDA kernels for `GATv2Conv` are necessary for running real-time spatial messaging across crypto asset nodes. |
| **Backend API** | **FastAPI** | High-performance ASGI framework with auto-generated OpenAPI documentation, fast JSON parsing, and native async support. Easily handles background tasks (async inference triggers). |
| **Frontend UI** | **Next.js 14 (TypeScript + Tailwind CSS + shadcn/ui)** | React framework offering Server-Side Rendering (SSR) and routing. Paired with Tailwind CSS for layout styling, `shadcn/ui` for premium modern component design, and `react-force-graph-2d` for interactive network visualizations. |
