"""ST-GCN Crypto Forecasting API — main application entry point."""

import sentry_sdk
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.core.config import settings
from app.api.routes import (
    assets, predictions, graph, risk, explain,
    forecast, status, coins, performance,
    correlations, sentiment_data, screener
)

# Initialize Sentry safely
if getattr(settings, 'sentry_dsn', None):
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1
    )

# Initialize LangSmith tracing
os.environ["LANGCHAIN_TRACING_V2"]  = settings.langchain_tracing_v2
if getattr(settings, 'langchain_api_key', None):
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
os.environ["LANGCHAIN_PROJECT"]     = settings.langchain_project

app = FastAPI(
    title="ST-GCN Crypto Forecasting API",
    description="Spatio-Temporal Graph Neural Network financial forecasting platform",
    version="1.0.0"
)

# CORS
origins = ["*"] if settings.environment == "development" else [os.getenv("FRONTEND_URL", "")]
app.add_middleware(
    CORSMiddleware, 
    allow_origins=origins,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Register routers
app.include_router(assets.router,      prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(graph.router,       prefix="/api")
app.include_router(risk.router,        prefix="/api")
app.include_router(explain.router,     prefix="/api")
app.include_router(forecast.router,      prefix="/api")
app.include_router(status.router,        prefix="/api")
app.include_router(coins.router,         prefix="/api")
app.include_router(performance.router,   prefix="/api")
app.include_router(correlations.router,  prefix="/api")
app.include_router(sentiment_data.router,prefix="/api")
app.include_router(screener.router,      prefix="/api")

@app.get("/health")
async def health():
    """Health check endpoint. Returns 200 OK with timestamp."""
    from datetime import datetime, timezone
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
