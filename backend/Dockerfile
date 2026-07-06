FROM python:3.12-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    if [ -f requirements-optional.txt ]; then pip install --no-cache-dir -r requirements-optional.txt || true; fi

# Add non-root user
RUN useradd -m cryptograph

# Copy backend code explicitly to avoid path ambiguity
COPY backend/app /app/app
COPY backend/scripts /app/scripts
COPY ml /app/ml
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini

# Set permissions
RUN chown -R cryptograph:cryptograph /app

# Switch to non-root user
USER cryptograph

# Ensure PYTHONPATH is set so that 'app' can be resolved
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
