# Contributing to CryptoGraph Analytics

Thank you for choosing to contribute to **CryptoGraph Analytics**! We welcome bug reports, pull requests, feedback, and architecture proposals to improve the system's analytical reliability and execution speed.

To maintain our core objective as a mathematically rigorous and verified single source of truth (SSOT), please follow these guidelines.

---

## 📂 Project Anatomy

The codebase is split into three main top-level directories:

* `/backend` — FastAPI application providing REST API endpoints, real-time WebSocket feeds, and data coordination.
* `/frontend` — Next.js 14 Web UI leveraging Tailwind CSS, Recharts, and Lightweight Charts for high-fidelity dashboards.
* `/ml` — Machine Learning core containing preprocessing logic, feature storage definitions, ST-GCN node extractors, and LSTM/Prophet model checkpoints.

---

## 🛠️ Development Sandbox Setup

### 1. Prerequisites
- **Python 3.11** or higher.
- **Node.js 18** or higher (with `npm` or `yarn`).
- **Docker & Docker Compose** (optional but highly recommended for containerized database validation).

### 2. Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On UNIX:
   source venv/bin/activate
   ```
3. Install package dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment variables template and configure them:
   ```bash
   cp .env.example .env
   ```
5. Initialize or populate the local database schema (see `DATABASE.md`):
   ```bash
   python app/db/populate_history.py
   ```
6. Start the local server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### 3. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd ../frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Copy the environment variables template:
   ```bash
   cp .env.example .env.local
   ```
4. Start the local development server:
   ```bash
   npm run dev
   ```
   The dashboard will be served at `http://localhost:3000`.

---

## 📏 Coding Standards

### 🐍 Backend Guidelines (Python)
* **Type Safety:** We enforce strict type-hinting across all modules. Function signatures must designate parameter and return types.
* **Authentication:** Every new API route under `/api/v1` (except public health checks and WebSocket handshakes) must be guarded with `Depends(verify_api_key)`.
* **Linting & Formatting:** We use **Ruff** for formatting and linting. Run Ruff before committing:
  ```bash
  ruff format .
  ruff check --fix .
  ```
* **Type Analysis:** We use **Mypy** to verify type consistency:
  ```bash
  mypy app/
  ```

### ⚛️ Frontend Guidelines (TypeScript & Next.js)
* **TypeScript Integrity:** Do not use `any`. Define strong interfaces and types for all component props, API response schemas, and state objects.
* **Theme Constraints:** Never hardcode colors in charts or layout structures. Always utilize the `useTheme` hook and the central `CHART_HEX` palette settings in `/lib/useChartPalette.ts`.
* **Aesthetics:** Ensure all dynamic layout panels utilize glassmorphism style rules, maintain grid geometry, and handle loading states elegantly without sudden layout shifts.

---

## 🧪 Testing Requirements

We rely on automated testing to prevent regressions. All changes must keep existing tests passing.

* **Backend Tests:** Run tests via `pytest` from the root or the `backend` folder:
  ```bash
  pytest
  ```
* **Data Quality Checks:** Run `backend/test_data_quality.py` to ensure that data invariants (e.g. no null prediction states, correct shapes) hold true.
* **Security & Vulnerabilities:** Ensure code doesn't introduce vulnerabilities by running **Bandit**:
  ```bash
  bandit -r app/
  ```

---

## 🚀 Pull Request Protocol

1. **Branching:** Base your work on the `main` branch. Use descriptive names like `feature/lstm-seq2seq-pad` or `bugfix/sentry-init`.
2. **Commit Messages:** Follow semantic guidelines (e.g., `feat: add multi-factor metrics to predictions endpoint` or `fix: remove deprecated verbose kwarg in prophet fit`).
3. **Local Audit:** Verify that tests, type checks, and formatting rules pass locally before opening a pull request.
4. **Documentation:** If you add endpoints, update `API_SPEC.md`. If you modify schemas, update `DATABASE.md`.
5. **PR Review:** All pull requests require review and passing automated CI checks before merging.
