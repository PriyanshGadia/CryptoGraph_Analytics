"""ST-GCN Crypto Forecasting API — main application entry point."""

import sentry_sdk
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.config import settings
from app.api.routes import (
    assets, predictions, graph, risk, explain,
    forecast, status, coins, performance,
    correlations, sentiment_data, screener, settings as app_settings_route,
    portfolio, stream
)
from app.db.database import engine, SessionLocal
from app.db.models_sqla import Base, AppSetting
from app.api.routes.forecast import limiter
from sqlalchemy import text

# Explicitly create technical_features to prevent Silent ORM failures on Android Termux
try:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS technical_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id VARCHAR NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                timestamp DATETIME NOT NULL,
                rsi_14 FLOAT,
                returns_1d FLOAT,
                returns_7d FLOAT,
                volatility_7d FLOAT,
                macd FLOAT,
                macd_signal FLOAT,
                atr_14 FLOAT,
                bb_width FLOAT,
                CONSTRAINT _tech_asset_timestamp_uc UNIQUE(asset_id, timestamp)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_technical_features_timestamp ON technical_features (timestamp)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_technical_features_id ON technical_features (id)"))
except Exception as e:
    print(f"Error ensuring technical_features table: {e}")

# Initialize Database
Base.metadata.create_all(bind=engine)

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
try:
    db_session = SessionLocal()
    frontend_url_record = db_session.query(AppSetting).filter(AppSetting.setting_key == "FRONTEND_URL").first()
    frontend_url = frontend_url_record.setting_value if frontend_url_record and frontend_url_record.setting_value else "http://localhost:3000"
    db_session.close()
except Exception:
    frontend_url = "http://localhost:3000"

origins = ["*"] if settings.environment == "development" else [frontend_url]
app.add_middleware(
    CORSMiddleware, 
    allow_origins=origins,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(app_settings_route.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(stream.router, prefix="/api")

@app.on_event("startup")
async def startup_event():
    import asyncio
    from app.api.routes.stream import SYMBOLS, prediction_broadcast_loop, screener_broadcast_loop
    from app.core.streams.binance_ws import binance_ws_loop, populate_static_features
    
    # Populate static cache using our synchronous DB session setup
    try:
        db = SessionLocal()
        populate_static_features(db, SYMBOLS)
        db.close()
    except Exception as e:
        print(f"Error populating static features: {e}")
        
    async def auto_refresh_loop():
        """Background task to run the scheduler automatically every hour."""
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
            print("[Scheduler] Auto-running hourly full data refresh...")
            try:
                db = SessionLocal()
                # 1. Refresh live technicals
                try:
                    from app.api.routes.screener import refresh_live_technicals
                    refresh_live_technicals(db=db)
                except Exception as e:
                    print(f"[Scheduler] Technicals error: {e}")
                
                # 2. Clear response cache
                try:
                    from app.core.cache import _cache
                    _cache.clear()
                except Exception as e:
                    print(f"[Scheduler] Cache error: {e}")
                    
                # 3. Trigger prediction broadcast
                try:
                    from app.api.routes.stream import FORCE_PREDICTION_BROADCAST
                    import app.api.routes.stream as stream_module
                    stream_module.FORCE_PREDICTION_BROADCAST = True
                except Exception as e:
                    print(f"[Scheduler] Broadcast error: {e}")
            except Exception as e:
                print(f"[Scheduler] Database session error: {e}")
            finally:
                db.close()
        
    # Start the async background loops
    asyncio.create_task(binance_ws_loop(SYMBOLS))
    asyncio.create_task(prediction_broadcast_loop())
    asyncio.create_task(screener_broadcast_loop())
    asyncio.create_task(auto_refresh_loop())

@app.get("/health")
async def health():
    """Health check endpoint. Returns 200 OK with timestamp."""
    from datetime import datetime, timezone
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
