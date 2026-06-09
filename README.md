# ST-GCN Crypto Forecasting Platform

A production-grade Spatio-Temporal Graph Neural Network (ST-GCN)
platform for cryptocurrency market forecasting with real-time data,
deep learning predictions, and AI-powered explanations.

## Features

- **50 Crypto Assets** tracked with live OHLCV data from Binance
- **ST-GCN Model** — Graph Neural Network analyzing asset correlations
- **LSTM + NeuralProphet Ensemble** — On-demand 7-day price forecasting
- **AI Explanations** — Groq LLaMA 3.3 explains every prediction
- **Network Graph** — Interactive force-directed correlation graph
- **Market Screener** — Filter assets by direction, confidence, sector
- **Performance Tracker** — Model accuracy, confusion matrix, calibration
- **Macro Dashboard** — VIX, Fed Rate, CPI impact analysis
- **Sentiment Analysis** — Fear & Greed + CoinGecko community data

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts, lightweight-charts |
| Backend | FastAPI, Python 3.11, Supabase |
| ML | PyTorch, PyTorch Geometric, NeuralProphet, SHAP |
| Database | Supabase (PostgreSQL) |
| LLM | Groq (LLaMA 3.3 70B) via LangChain |
| Tracking | Weights & Biases |
| Monitoring | Sentry |

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase account (free tier works)
- API keys (see Setup section)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/AkshatJ557/CryptoGraph_Analytics.git
cd CryptoGraph_Analytics
```

### 2. Get your API keys

You need these free API keys:

| Service | Free Tier | Get Key At |
|---------|-----------|-----------|
| Supabase | 500MB DB, 2GB bandwidth | https://supabase.com |
| Groq | 14,400 req/day | https://console.groq.com |
| Binance | Public market data | https://binance.com/api |
| FRED | Economic data | https://fred.stlouisfed.org/docs/api/api_key.html |
| Weights & Biases | Free for personal use | https://wandb.ai |
| Sentry | 5K errors/month free | https://sentry.io |

### 3. Set up environment files

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env and fill in your keys

# ML pipeline
cp ml/.env.example ml/.env
# Edit ml/.env and fill in your keys

# Frontend
cp frontend/.env.example frontend/.env.local
# Edit frontend/.env.local and fill in your keys
```

### 4. Set up the database

Go to your Supabase project → SQL Editor and run each file in order:

```bash
# Run these SQL files in Supabase SQL Editor:
database/migrations/001_create_assets.sql
database/migrations/002_create_ohlcv.sql
database/migrations/003_create_sentiment.sql
database/migrations/004_create_predictions.sql
database/migrations/005_create_graph_snapshots.sql
database/migrations/006_create_feature_store.sql
```

### 5. Install dependencies

```bash
# Backend
cd backend && pip install -r requirements.txt

# ML pipeline
cd ml && pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

### 6. Collect initial data (run once)

```bash
cd ml

# Enrich asset metadata (sectors + market caps)
python3 data/ingestion/enrich_assets.py

# Collect historical OHLCV (takes 30-60 minutes for full history)
python3 data/ingestion/binance_collector.py

# Collect macro data
python3 data/ingestion/fred_collector.py

# Collect fear & greed history
python3 data/ingestion/fear_greed_collector.py

# Collect sentiment
python3 data/ingestion/sentiment_collector.py

# Compute technical features
python3 data/feature_engineering/technical_indicators.py
python3 data/feature_engineering/sentiment_features.py
python3 data/feature_engineering/macro_features.py

# Seed mock predictions (to populate dashboard immediately)
python3 pipelines/mock_inference.py
python3 pipelines/seed_graph_snapshots.py
```

### 7. Run the platform

Open 3 terminal windows:

```bash
# Terminal 1: Backend API
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Data scheduler (keeps data fresh automatically)
cd ml && python3 scheduler.py
```

Visit **http://localhost:3000**

### 8. Run with Docker (alternative)

```bash
docker-compose up --build
```

## Project Structure
CryptoGraph_Analytics/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/routes/        # All API endpoints
│   │   ├── core/              # Config, security, cache
│   │   └── db/                # Supabase client, models
│   ├── requirements.txt
│   └── .env.example           # Copy to .env
│
├── ml/                        # ML pipeline
│   ├── data/
│   │   ├── ingestion/         # Data collectors
│   │   ├── feature_engineering/
│   │   └── feature_store/
│   ├── graph/                 # Graph construction
│   ├── models/                # ST-GCN, LSTM, forecast
│   ├── training/              # Trainer, loss, metrics
│   ├── pipelines/             # ETL, training, inference
│   ├── scheduler.py           # Auto data refresh
│   ├── requirements.txt
│   └── .env.example           # Copy to .env
│
├── frontend/                  # Next.js 14 frontend
│   ├── app/                   # App router pages
│   │   ├── market/            # 50 asset cards
│   │   ├── coin/[symbol]/     # Individual coin page
│   │   ├── graph/             # Network graph
│   │   ├── correlations/      # Correlation heatmap
│   │   ├── predictions/       # Predictions + LSTM forecast
│   │   ├── performance/       # Model accuracy tracker
│   │   ├── screener/          # Market scanner
│   │   ├── sentiment/         # Fear & Greed analysis
│   │   ├── risk/              # Risk dashboard + macro
│   │   └── explain/           # AI explanations
│   ├── components/            # Shared UI components
│   ├── lib/                   # API client, Supabase client
│   ├── package.json
│   └── .env.example           # Copy to .env.local
│
├── database/
│   └── migrations/            # SQL files to run in Supabase
│
├── .github/
│   └── workflows/             # CI/CD pipelines
│
├── docker-compose.yml
├── Makefile
└── README.md
## Pages

| Page | URL | Description |
|------|-----|-------------|
| Market Overview | /market | All 50 assets with predictions |
| Coin Detail | /coin/BTC | Candlestick chart, indicators, history |
| Network Graph | /graph | Force-directed correlation graph |
| Correlations | /correlations | 50×50 heatmap |
| Predictions | /predictions | Table + LSTM forecast on demand |
| Performance | /performance | Model accuracy, confusion matrix |
| Screener | /screener | Filter assets by any criterion |
| Sentiment | /sentiment | Fear & Greed analysis |
| Risk Dashboard | /risk | Market regime + macro indicators |
| Explain AI | /explain | Groq LLaMA explanations |

## API Endpoints
GET  /health                          Health check
GET  /api/assets                      All 50 assets with predictions
GET  /api/predictions                 Latest predictions
GET  /api/graph/latest                Graph for visualization
GET  /api/risk                        Risk dashboard data
GET  /api/risk/macro                  Macro economic data
GET  /api/explain/{symbol}            AI explanation via Groq
GET  /api/forecast/{symbol}           LSTM+NeuralProphet forecast
GET  /api/coins/{symbol}/ohlcv        Candlestick data
GET  /api/coins/{symbol}/indicators   Technical indicators
GET  /api/coins/{symbol}/correlations Top correlated assets
GET  /api/performance                 Model accuracy metrics
GET  /api/correlations/matrix         50x50 correlation matrix
GET  /api/screener                    Filtered asset screener
GET  /api/sentiment-data/*            Sentiment analysis data
GET  /api/status                      Data freshness status
## Data Refresh Schedule

The scheduler (ml/scheduler.py) automatically keeps data fresh:

| Data | Frequency |
|------|-----------|
| OHLCV prices | Every 5 minutes |
| Sentiment | Every 1 hour |
| Fear & Greed | Every 1 hour |
| Technical features | Every 6 hours |
| Predictions | Every 24 hours |
| Graph snapshots | Every 24 hours |

## Troubleshooting

**Binance rate limits:** The collector handles these automatically with
exponential backoff. Some symbols (REN, WAVES) may be delisted —
this is expected and handled gracefully.

**CoinGecko 429 errors:** The sentiment collector sleeps 1.5s between
requests. 60s sleep on 429. This is normal — let it run.

**Supabase IPv6 only (free tier):** Direct psycopg2 connections require
the connection pooler URL (Settings → Database → Use connection pooling).
The supabase-py client works fine on free tier for all DML operations.

**Prophet installation fails:** Use NeuralProphet instead:
pip install neuralprophet==0.9.0

**No predictions showing:** Run mock_inference.py first:
cd ml && python3 pipelines/mock_inference.py

## License

MIT License — see LICENSE file.
