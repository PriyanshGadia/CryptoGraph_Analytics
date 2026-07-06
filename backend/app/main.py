"""ST-GCN Crypto Forecasting API — main application entry point. Trigger reload."""

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

# SQLite migration: rename zk_snark_proof to attestation_hash if needed
try:
    with engine.begin() as conn:
        table_exists = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'")).fetchone()
        if table_exists:
            columns = conn.execute(text("PRAGMA table_info(predictions)")).fetchall()
            column_names = [col[1] for col in columns]
            if "zk_snark_proof" in column_names and "attestation_hash" not in column_names:
                print("[Migration] Renaming predictions.zk_snark_proof to attestation_hash...")
                conn.execute(text("ALTER TABLE predictions RENAME COLUMN zk_snark_proof TO attestation_hash"))
except Exception as e:
    print(f"Error checking/renaming predictions column: {e}")

# Initialize Database
Base.metadata.create_all(bind=engine)

# Initialize Sentry safely
if getattr(settings, 'sentry_dsn', None):
    dsn_str = settings.sentry_dsn.strip()
    if dsn_str and "project_id" not in dsn_str and "your_sentry_dsn" not in dsn_str:
        try:
            sentry_sdk.init(
                dsn=dsn_str,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1
            )
        except Exception as e:
            print(f"Warning: Sentry initialization failed: {e}")
    else:
        print("Sentry initialization skipped (DSN is placeholder or empty).")

# Initialize LangSmith tracing
os.environ["LANGCHAIN_TRACING_V2"]  = settings.langchain_tracing_v2
if getattr(settings, 'langchain_api_key', None):
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
os.environ["LANGCHAIN_PROJECT"]     = settings.langchain_project

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
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
        
    if os.getenv("TESTING") == "True":
        print("[Lifespan] WebSocket background tasks bypassed in testing mode.")
        yield
        return
        
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

                # 3b. Refresh SSOT prediction cache so /api/assets reflects fresh confidence
                try:
                    from app.core.streams.binance_ws import refresh_predictions_in_ssot
                    refresh_predictions_in_ssot(db)
                    print("[Scheduler] SSOT prediction cache refreshed.")
                except Exception as e:
                    print(f"[Scheduler] SSOT refresh error: {e}")
            except Exception as e:
                print(f"[Scheduler] Database session error: {e}")
            finally:
                db.close()

    # Start tasks
    binance_task = asyncio.create_task(binance_ws_loop(SYMBOLS))
    prediction_task = asyncio.create_task(prediction_broadcast_loop())
    screener_task = asyncio.create_task(screener_broadcast_loop())
    refresh_task = asyncio.create_task(auto_refresh_loop())
    
    yield
    
    # Clean shutdown
    binance_task.cancel()
    prediction_task.cancel()
    screener_task.cancel()
    refresh_task.cancel()
    await asyncio.gather(binance_task, prediction_task, screener_task, refresh_task, return_exceptions=True)

app = FastAPI(
    title="ST-GCN Crypto Forecasting API",
    description="Spatio-Temporal Graph Neural Network financial forecasting platform",
    version="1.0.0",
    lifespan=lifespan
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

# Lifespan context manager runs tasks automatically. No on_event('startup') needed.

@app.get("/health")
async def health():
    """Health check endpoint. Returns 200 OK with timestamp."""
    from datetime import datetime, timezone
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
