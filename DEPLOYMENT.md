# Deployment & Infrastructure Specification

This document details the configuration for local portability, desktop automation, mobile (Termux) deployment, and production split-stack cloud hosting.

---

## 1. Local One-Click Portability

To guarantee that the project can be spun up on any user's machine without dependency hell or missing runtime errors, we provide automated native installers and Docker solutions.

### 1.1 Native Automated Installers (Recommended for local dev)
These scripts check if the required environments (Node.js, Python, npm) are present. If not, they automatically download and install them using the native OS package managers (`winget`, `brew`, `apt`), build the isolated virtual environments, and boot the application.

- **Windows**: `start.bat` acts as a proxy for `install_windows.ps1`
  - *Under the hood*: Uses `winget` to fetch Python 3.11 and Node.js. Automatically sets up the `venv`.
- **macOS / Linux**: `start.sh` proxies to `install_unix.sh`
  - *Under the hood*: Uses `brew` (macOS) or `apt` (Linux) to install dependencies.
- **Android (Termux)**: `termux_start.sh`
  - *Under the hood*: Uses `pkg` to install ARM-compatible binaries (`python`, `nodejs`, `rust`, `binutils`), resolving complex ML compilation errors on mobile devices before starting.

### 1.2 Docker Environment
The project is fully containerized. If a user simply has Docker Desktop installed, they can bypass all native installation checks.

```bash
docker-compose up --build
```
This spins up:
- `backend` container on port `8000` (FastAPI)
- `frontend` container on port `3000` (Next.js)

---

## 2. Cloud Production Architecture (Split-Stack)

**CRITICAL ISSUE**: The Vercel platform enforces a strict 250MB limit on serverless functions. Because the ST-GCN backend relies on PyTorch (800MB+), Numpy, SciPy, and other heavy ML libraries, the backend **cannot** be deployed to Vercel Serverless. If attempted, Vercel will drop the backend silently, leaving an empty shell frontend.

**SOLUTION**: We use a split-stack cloud architecture.

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
```

### 2.1 Backend Deployment (Render.com)
The backend is designed to be 1-click deployed to Render.com using Infrastructure-as-Code via the `render.yaml` file located in the root directory.

- **Deployment Method**: Connect Render to your GitHub repo, and Render will automatically parse `render.yaml`.
- **Runtime**: Python Web Service.
- **Disk**: Mounts a 1GB persistent disk at `/opt/render/project/src/backend/database` to safely persist the SQLite database across redeployments.
- **Scaling**: Fully handles ML and Web Sockets via Uvicorn.

### 2.2 Frontend Deployment (Vercel.com)
The frontend remains on Vercel for edge-cached Next.js delivery.

- **Deployment Method**: Import the repository into Vercel and set the Framework Preset to Next.js.
- **Routing Rules**: Vercel reads the included `frontend/vercel.json` to handle Next.js rewrites and production rules.
- **Environment Variable**: You MUST set `NEXT_PUBLIC_API_URL` in your Vercel project settings to point to your new Render backend URL (e.g., `https://cryptograph-backend.onrender.com`).

---

## 3. GitHub Actions CI/CD Workflows

### 3.1 Continuous Integration (`ci.yml`)
Triggered on pull requests and pushes to the `main` branch.
- **Tasks**: Installs Python and Node dependencies, runs `ruff`, executes PyTest, and verifies `npm run build` succeeds.

### 3.2 Continuous Deployment (`deploy.yml`)
- Triggers a Render webhook (`curl -X POST https://api.render.com/deploy/srv-...`)
- Deploys the frontend to Vercel using the Vercel CLI tool.

---

## 4. Environment Variables

### 4.1 Backend (`backend/.env` or Render Dashboard)
- `BINANCE_API_KEY`, `BINANCE_SECRET`
- `GROQ_API_KEY` (For LLaMA 3 explanation models)
- `FRED_API_KEY`

### 4.2 Frontend (`frontend/.env.local` or Vercel Dashboard)
- `NEXT_PUBLIC_API_URL`: Points to your Render API. Fallbacks to `http://localhost:8000` locally.
