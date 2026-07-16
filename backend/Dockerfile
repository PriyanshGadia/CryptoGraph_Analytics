# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    if [ -f requirements-optional.txt ]; then pip install --no-cache-dir --prefix=/install -r requirements-optional.txt || true; fi

# Stage 2: Final runner image
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime dependencies (curl for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user
RUN useradd -m cryptograph && \
    mkdir -p /app/database /data && \
    chown -R cryptograph:cryptograph /app /data

# Copy python packages from builder
COPY --from=builder --chown=cryptograph:cryptograph /install /usr/local

# Copy backend code explicitly
COPY --chown=cryptograph:cryptograph backend/app /app/app
COPY --chown=cryptograph:cryptograph backend/scripts /app/scripts
COPY --chown=cryptograph:cryptograph backend/seed_trades.py /app/seed_trades.py
COPY --chown=cryptograph:cryptograph ml /app/ml
COPY --chown=cryptograph:cryptograph backend/alembic /app/alembic
COPY --chown=cryptograph:cryptograph backend/alembic.ini /app/alembic.ini

# Switch to non-root user
USER cryptograph

# Ensure PYTHONPATH is set so that 'app' and 'ml' can be resolved
ENV PYTHONPATH=/app

# Store the SQLite database on the persistent volume
ENV DATABASE_PATH=/data/cryptograph.db

# Declare persistent volume for the SQLite database
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
