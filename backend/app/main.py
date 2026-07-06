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

# Move lazy imports here
import os
import sys
from app.api.routes.stream import SYMBOLS, prediction_broadcast_loop, screener_broadcast_loop, get_refresh_event
from app.core.streams.binance_ws import binance_ws_loop, populate_static_features, refresh_predictions_in_ssot
from app.api.routes.screener import refresh_live_technicals
from app.core.cache import _cache
scripts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if scripts_path not in sys.path:
    sys.path.append(scripts_path)
from enrich_assets import enrich_assets

# Initialize Sentry safely
if getattr(settings, 'sentry_dsn', None) and settings.sentry_dsn.strip():
    dsn_str = settings.sentry_dsn.strip()
    if dsn_str.startswith("http") and "@" in dsn_str:  # Basic DSN format validation
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
        logger.info("Sentry initialization skipped (DSN is invalid or placeholder).")

@asynccontextmanager
async def lifespan(app: FastAPI):
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
        
    # Set up proper cron-like scheduler for background tasks
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    
    async def scheduled_refresh_job():
        """Scheduled hourly refresh executed by APScheduler."""
        logger.info("[Scheduler] Auto-running hourly full data refresh...")
        try:
            db = SessionLocal()
            
            # 1a. Enrich Asset Metadata
            try:
                await asyncio.to_thread(enrich_assets)
            except Exception as e:
                logger.error(f"[Scheduler] Asset enrichment error: {e}", exc_info=True)
            
            # 1b. Refresh live technicals
            try:
                await asyncio.to_thread(refresh_live_technicals, db)
            except Exception as e:
                logger.error(f"[Scheduler] Technicals error: {e}", exc_info=True)
            
            # 2. Clear response cache
            try:
                _cache.clear()
            except Exception as e:
                logger.error(f"[Scheduler] Cache error: {e}")
                
            # 3. Trigger prediction broadcast
            try:
                get_refresh_event().set()
            except Exception as e:
                logger.error(f"[Scheduler] Broadcast error: {e}")

            # 3b. Refresh SSOT prediction cache so /api/assets reflects fresh confidence
            try:
                refresh_predictions_in_ssot(db)
                logger.info("[Scheduler] SSOT prediction cache refreshed.")
            except Exception as e:
                logger.error(f"[Scheduler] SSOT refresh error: {e}")
        except Exception as e:
            logger.error(f"[Scheduler] Database session error: {e}")
        finally:
            try:
                db.close()
            except:
                pass

    # Schedule the refresh job to run every hour
    scheduler.add_job(scheduled_refresh_job, 'interval', hours=1, max_instances=1)
    scheduler.start()

    # Start WebSocket tasks
    binance_task = asyncio.create_task(binance_ws_loop(SYMBOLS))
    prediction_task = asyncio.create_task(prediction_broadcast_loop())
    screener_task = asyncio.create_task(screener_broadcast_loop())
    
    try:
        yield
    finally:
        # Clean shutdown using shield to prevent brutal termination
        logger.info("[Lifespan] Shutting down services safely...")
        try:
            scheduler.shutdown(wait=False)
        except Exception as e:
            logger.error(f"[Lifespan] Error shutting down scheduler: {e}")
        
        binance_task.cancel()
        prediction_task.cancel()
        screener_task.cancel()
        
        for task in [binance_task, prediction_task, screener_task]:
            try:
                # Shield the cleanup so it isn't interrupted by uvicorn's strict timeout
                await asyncio.shield(asyncio.wait_for(task, timeout=2.0))
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error(f"[Lifespan] Error awaiting cancelled task: {e}")

app = FastAPI(
    title="ST-GCN Crypto Forecasting API",
    description="Spatio-Temporal Graph Neural Network financial forecasting platform",
    version="1.0.0",
    lifespan=lifespan
)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

dynamic_origins = ["*"] if settings.environment == "development" else [get_setting("FRONTEND_URL", "http://localhost:3000")]

# Initialize CORS Middleware at module creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=dynamic_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)



from slowapi.middleware import SlowAPIMiddleware

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

from fastapi import Depends
from app.api.deps import verify_api_key

# Register routers with global authentication
app.include_router(assets.router,      prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(predictions.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(graph.router,       prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(risk.router,        prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(explain.router,     prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(forecast.router,    prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(status.router,      prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(coins.router,       prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(performance.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(correlations.router,prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(sentiment_data.router,prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(screener.router,    prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(app_settings_route.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(portfolio.router,   prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(stream.router,      prefix="/api", dependencies=[Depends(verify_api_key)])

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
