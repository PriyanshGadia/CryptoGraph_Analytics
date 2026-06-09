# Deployment & Infrastructure Specification

This document details the configuration for local deployment, production hosting, automated CI/CD pipelines, and environment configuration management.

---

## 1. Local Environment Deployment

The local stack runs on a multi-container Docker compose architecture to replicate API and frontend services locally.

### 1.1 Docker Compose Configuration (`docker-compose.yml`)
Spins up the FastAPI backend and Next.js frontend. The ML worker can be executed inside the backend container or triggered as a command line run.

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ml_artifacts:/app/artifacts
      - ./backend/.env:/app/.env
    environment:
      - ENVIRONMENT=development
      - PORT=8000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

volumes:
  ml_artifacts:
```

### 1.2 Execution Commands
- Build and spin up the containers:
  ```bash
  docker-compose up --build
  ```
- Run the ETL pipeline manually inside the backend container to ingest data:
  ```bash
  docker-compose exec backend python -m ml.pipelines.etl_pipeline
  ```

---

## 2. Production Environment Architecture

For production, components are separated to optimize scalability, cost, and reliability.

```text
  +-------------------------+                 +------------------------+
  |    Frontend (Vercel)    |                 |   Supabase Cloud DB    |
  |  - Serves Next.js App   |<--------------->|  - Serves Postgres DB  |
  |  - REST queries Render  |  (Direct Read)  |  - Manages RLS access  |
  +------------+------------+                 +-----------+------------+
               |                                          ^
               | (JSON API Requests)                      |
               v                                          | (Query / Upsert)
  +-------------------------+                             |
  |     Backend (Render)    |-----------------------------+
  |  - Docker Container     |
  |  - Auto-scales Web API  |
  +-------------------------+
               ^
               | (Deploys model)
  +------------+------------+
  |    ML Worker (Render)   |
  |  - Background Worker    |
  |  - Daily Cron Job       |
  |  - Runs ETL & Training  |
  +-------------------------+
```

### 2.1 Backend Web Service (Render)
- **Deployment Method**: Web Service running a Docker build.
- **Port**: `8000` (FastAPI).
- **Environment**: Production.
- **Storage Disk**: A persistent volume (`/app/artifacts`) must be mounted to save model weights (`best_model.pt`) between redeployments, unless configured to save directly to an external store like AWS S3 or W&B.

### 2.2 Frontend Server (Vercel)
- **Deployment Method**: Serverless Deployment (standard Next.js target).
- **Framework Preset**: Next.js.
- **Environment Variable**: Set `NEXT_PUBLIC_API_URL` to point to the Render web service URL.

### 2.3 ML Pipelines Background Worker (Render)
- **Deployment Method**: Background Worker.
- **Runtime**: Python 3.11.
- **Schedule**: Cron configuration `0 1 * * *` (Daily execution at 1:00 AM UTC).
- **Execution Target**: Runs `python ml/pipelines/etl_pipeline.py` daily to ingest data, and exposes an endpoint or command to run training periodically.

---

## 3. GitHub Actions CI/CD Workflows

### 3.1 Continuous Integration (`ci.yml`)
Triggered on pull requests and pushes to the `main` branch.

- **Tasks**:
  1. Installs Python dependencies for Backend and ML.
  2. Runs code linter (`ruff check .`).
  3. Executes backend tests via `pytest` (`backend/tests/`).
  4. Executes ML unit tests (`ml/tests/`) (excluding long integration/training cycles).
  5. Installs Node.js, runs frontend code quality checks (`npm run lint`), and verifies Next.js builds successfully (`npm run build`).

### 3.2 Continuous Deployment (`deploy.yml`)
Triggered automatically on commits to the `main` branch after CI succeeds.

- **Tasks**:
  1. Triggers Render build via Webhook URL deployment trigger.
     ```bash
     curl -X POST https://api.render.com/deploy/srv-xxxx?key=yyyy
     ```
  2. Builds and Deploys the frontend application to Vercel production using the Vercel CLI tool.

---

## 4. Environment Variables & Secret Configuration

To prevent leaks, environment variables are partitioned and stored in hosting environment panels.

### 4.1 Backend App Environment variables (`backend/.env`)
- `ENVIRONMENT` (`production` / `development`)
- `SUPABASE_URL` (Supabase API URI)
- `SUPABASE_SERVICE_ROLE_KEY` (Supabase administrative DB bypass key)
- `GROQ_API_KEY` (Groq API key for model explanation)
- `LANGCHAIN_API_KEY` (LangChain API key for tracing)
- `LANGCHAIN_TRACING_V2` (`true` / `false`)
- `LANGCHAIN_PROJECT` (`stgcn-crypto`)
- `SENTRY_DSN` (Sentry API DSN for API error reporting)

### 4.2 ML pipeline Environment variables (`ml/.env`)
- `SUPABASE_URL` (Supabase API URI)
- `SUPABASE_SERVICE_ROLE_KEY` (Admin key to write features/predictions)
- `BINANCE_API_KEY` (Binance exchange key)
- `BINANCE_SECRET` (Binance signature secret)
- `FRED_API_KEY` (Federal Reserve Economic Data API key)
- `WANDB_API_KEY` (Weights & Biases API credential)
- `SENTRY_DSN` (Sentry API DSN for script crashes)

### 4.3 Frontend UI Client Environment variables (`frontend/.env.local`)
- `NEXT_PUBLIC_API_URL` (URL of the active FastAPI backend)
- `NEXT_PUBLIC_SUPABASE_URL` (Supabase public URL)
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` (Supabase client-safe public key)

---

## 5. Health Check & Error Monitoring Strategy

- **Service Live Status**: Ping GET `/health` on the FastAPI server. This endpoint is tracked by Render to coordinate zero-downtime rolling updates.
- **Application Crushes**: The FastAPI application utilizes the Sentry SDK middleware to automatically intercept and log unhandled exceptions (500 errors).
- **ML Scripts Logging**: Pipeline executions (`etl_pipeline.py`, `training_pipeline.py`) wrap run-loops in try-except statements. Standard errors are piped to standard out, and severe errors trigger Sentry logging events.
- **API Chains Monitoring**: LangSmith tracing tracks ChatGroq invocation speed, prompt layouts, and response token usages.
