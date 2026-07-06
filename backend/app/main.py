"""ST-GCN Crypto Forecasting API — main application entry point. Trigger reload."""

import sentry_sdk
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.routes import (
    assets, predictions, graph, risk, explain,
    forecast, status, coins, performance,
    correlations, sentiment_data, screener, settings as app_settings_route,
    portfolio, stream
)
from app.db.database import SessionLocal
from app.db.models_sqla import AppSetting
from app.api.routes.forecast import limiter

import logging
import asyncio
from contextlib import asynccontextmanager

from app.core.config import settings, get_setting

# Set up structured logging
logging.basicConfig(
    level=logging.INFO if settings.environment == "production" else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cryptograph")

# Initialize Sentry safely
if getattr(settings, 'sentry_dsn', None) and settings.sentry_dsn.strip():
    dsn_str = settings.sentry_dsn.strip()
    if "your_sentry_dsn" not in dsn_str:
        try:
            sentry_sdk.init(
                dsn=dsn_str,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1
            )
            logger.info("Sentry initialized successfully.")
        except Exception as e:
            logger.error(f"Sentry initialization failed: {e}")
    else:
        logger.info("Sentry initialization skipped (DSN is placeholder).")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    import asyncio
    from app.api.routes.stream import SYMBOLS, prediction_broadcast_loop, screener_broadcast_loop
    from app.core.streams.binance_ws import binance_ws_loop, populate_static_features
    from app.core.config import get_setting
    
    # Startup Security Validation: Ensure API_KEY is set or fail closed
    api_key_configured = get_setting("api_key")
    if not api_key_configured:
        logger.error("[SECURITY ERROR] API_KEY is not configured. Server startup aborted to prevent vulnerabilities.")
        raise RuntimeError("API_KEY must be configured to start the server.")
    
    # Populate static cache using our synchronous DB session setup
    try:
        db = SessionLocal()
        populate_static_features(db, SYMBOLS)
        db.close()
    except Exception as e:
        logger.error(f"Error populating static features: {e}", exc_info=True)
        
    if os.getenv("TESTING") == "True":
        print("[Lifespan] WebSocket background tasks bypassed in testing mode.")
        yield
        return
        
    refresh_lock = asyncio.Lock()
    async def auto_refresh_loop():
        """Background task to run the scheduler automatically every hour."""
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
            
            if refresh_lock.locked():
                logger.warning("[Scheduler] Previous refresh is still running. Skipping this iteration to prevent overlap.")
                continue
                
            async with refresh_lock:
                logger.info("[Scheduler] Auto-running hourly full data refresh...")
                try:
                    db = SessionLocal()
                    
                    # 1a. Enrich Asset Metadata
                    try:
                        import sys
                        import os
                        scripts_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
                        sys.path.append(scripts_path)
                        from enrich_assets import enrich_assets
                        enrich_assets()
                    except Exception as e:
                        logger.error(f"[Scheduler] Asset enrichment error: {e}")
                    
                    # 1b. Refresh live technicals
                    try:
                        from app.api.routes.screener import refresh_live_technicals
                        refresh_live_technicals(db=db)
                    except Exception as e:
                        logger.error(f"[Scheduler] Technicals error: {e}")
                    
                    # 2. Clear response cache
                    try:
                        from app.core.cache import _cache
                        _cache.clear()
                    except Exception as e:
                        logger.error(f"[Scheduler] Cache error: {e}")
                        
                    # 3. Trigger prediction broadcast
                    try:
                        from app.api.routes.stream import get_refresh_event
                        get_refresh_event().set()
                    except Exception as e:
                        logger.error(f"[Scheduler] Broadcast error: {e}")

                    # 3b. Refresh SSOT prediction cache so /api/assets reflects fresh confidence
                    try:
                        from app.core.streams.binance_ws import refresh_predictions_in_ssot
                        refresh_predictions_in_ssot(db)
                        logger.info("[Scheduler] SSOT prediction cache refreshed.")
                    except Exception as e:
                        logger.error(f"[Scheduler] SSOT refresh error: {e}")
                except Exception as e:
                    logger.error(f"[Scheduler] Database session error: {e}")
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
    
    for task in [binance_task, prediction_task, screener_task, refresh_task]:
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

app = FastAPI(
    title="ST-GCN Crypto Forecasting API",
    description="Spatio-Temporal Graph Neural Network financial forecasting platform",
    version="1.0.0",
    lifespan=lifespan
)

dynamic_origins = ["*"] if settings.environment == "development" else [get_setting("FRONTEND_URL", "http://localhost:3000")]

# Initialize CORS Middleware at module creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=dynamic_origins,
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
    """Health check endpoint. Returns 200 OK with timestamp and DB status."""
    from datetime import datetime, timezone
    from sqlalchemy import text
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db_status = "unhealthy"
        
    return {"status": "ok", "db": db_status, "timestamp": datetime.now(timezone.utc).isoformat()}
