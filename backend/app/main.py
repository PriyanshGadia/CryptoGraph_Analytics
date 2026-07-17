"""Crypto Ensemble Forecaster API — main application entry point. Trigger reload."""

import os
import sys
# Add backend dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add project root for the ml/ package
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.routes import (
    assets, graph, explain,
    forecast, status, coins, performance,
    correlations, sentiment_data, screener, settings as app_settings_route,
    portfolio, stream, predictions, risk, scheduler, auth
)
from app.db.database import SessionLocal
from app.core.limiter import limiter

import logging
import asyncio
from contextlib import asynccontextmanager
from pythonjsonlogger import jsonlogger

from app.core.config import settings, get_setting

# Set up structured JSON logging
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Keep root at INFO to prevent library spam

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Only set our specific application logger to DEBUG if in dev mode
app_logger = logging.getLogger("cryptograph")
app_logger.setLevel(logging.INFO if settings.environment == "production" else logging.DEBUG)
logger = app_logger

# Silence ultra-verbose third party loggers
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)

# Move lazy imports here
import os
from app.api.routes.stream import SYMBOLS, prediction_broadcast_loop, screener_broadcast_loop, get_refresh_event
from app.core.streams.binance_ws import binance_ws_loop, populate_static_features, refresh_predictions_in_ssot
from app.api.routes.screener import refresh_live_technicals
from app.services.enrich_assets import enrich_assets
from app.core.cache import _cache

# Initialize Sentry safely without crashing on failure
if getattr(settings, 'sentry_dsn', None) and settings.sentry_dsn.strip():
    dsn_str = settings.sentry_dsn.strip()
    if "project_id" in dsn_str or "your_sentry_dsn" in dsn_str:
        logger.info("Sentry initialization skipped (placeholder DSN detected).")
    else:
        try:
            from circuitbreaker import circuit
            @circuit(failure_threshold=2, recovery_timeout=30)
            def init_sentry():
                import sentry_sdk
                from sentry_sdk.integrations.fastapi import FastApiIntegration
                sentry_sdk.init(
                    dsn=dsn_str,
                    environment=settings.environment,
                    integrations=[FastApiIntegration()],
                    traces_sample_rate=0.1
                )
            
            init_sentry()
            logger.info("Sentry initialized successfully.")
        except Exception as e:
            logger.error(f"Sentry initialization failed (Circuit Broken): {e}. Continuing without monitoring.")
else:
    logger.info("Sentry initialization skipped (DSN is missing).")

enrich_assets_lock = asyncio.Lock()

async def run_database_seeder():
    """Background task to seed the database with assets and trades if it's empty."""
    import sys
    import os
    from pathlib import Path
    logger.info("[Seeder] Starting database self-seeding in background...")
    try:
        base_dir = Path(__file__).resolve().parent.parent
        quick_seed_path = base_dir / "scripts" / "quick_seed.py"
        seed_trades_path = base_dir / "seed_trades.py"
        
        env = os.environ.copy()
        
        # 1. Run quick_seed.py
        logger.info(f"[Seeder] Executing quick_seed.py at {quick_seed_path}")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(quick_seed_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(base_dir),
            env=env
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"[Seeder] quick_seed.py failed with code {proc.returncode}")
            logger.error(f"[Seeder] stdout: {stdout.decode(errors='replace')}")
            logger.error(f"[Seeder] stderr: {stderr.decode(errors='replace')}")
            return
        logger.info("[Seeder] quick_seed.py completed successfully.")
        
        # 2. Run seed_trades.py
        logger.info(f"[Seeder] Executing seed_trades.py at {seed_trades_path}")
        proc2 = await asyncio.create_subprocess_exec(
            sys.executable, str(seed_trades_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(base_dir),
            env=env
        )
        stdout2, stderr2 = await proc2.communicate()
        if proc2.returncode != 0:
            logger.error(f"[Seeder] seed_trades.py failed with code {proc2.returncode}")
            logger.error(f"[Seeder] stdout: {stdout2.decode(errors='replace')}")
            logger.error(f"[Seeder] stderr: {stderr2.decode(errors='replace')}")
            return
        logger.info("[Seeder] seed_trades.py completed successfully.")
        
        # 3. Refresh SSOT state
        logger.info("[Seeder] Seeding finished. Refreshing in-memory SSOT state...")
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            from app.api.routes.stream import SYMBOLS as stream_symbols
            # Re-read symbols from DB
            from app.db.models import Asset
            assets = db.query(Asset.symbol).all()
            symbols_list = [a.symbol for a in assets] if assets else stream_symbols
            
            # Re-populate features and predict cache
            populate_static_features(db, symbols_list)
            
            # Recompute correlations if possible
            try:
                from app.api.routes.correlations import precompute_correlations_sync
                precompute_correlations_sync(db)
            except Exception as ce:
                logger.error(f"[Seeder] Failed to precompute correlations: {ce}")
                
            logger.info("[Seeder] SSOT state refreshed successfully.")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"[Seeder] Error during background seeding: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("========================================")
    logger.info("CryptoGraph Analytics API Starting Up...")
    logger.info("INFO: Running in single-worker stateless-in-memory mode optimized for low-memory (3GB) local environments.")
    logger.info("========================================")

    # Startup Security Validation: Ensure API_KEY is set and strongly entropic
    api_key_configured = get_setting("api_key")
    import re
    
    if not api_key_configured:
        default_fallback_key = "dev_default_secure_key_1234567890"
        logger.warning(f"[SECURITY ALERT] No API_KEY configured. Falling back to default secure developer key: {default_fallback_key}")
        logger.warning("Please save this key and configure it in your environment for production.")
        os.environ["API_KEY"] = default_fallback_key
        api_key_configured = default_fallback_key
    else:
        api_key_configured = api_key_configured.strip()
    
    if len(api_key_configured) < 32 or not re.match(r"^[a-zA-Z0-9_\-]+$", api_key_configured):
        logger.error("[SECURITY ERROR] API_KEY is too weak. Must be >= 32 characters and URL-safe alphanumeric.")
        raise RuntimeError("API_KEY must be configured with at least 32 characters and high entropy.")
    
    # Startup CORS Validation
    frontend_url = get_setting("FRONTEND_URL")
    if settings.environment == "production":
        if not frontend_url or frontend_url == "http://localhost:3000":
            logger.error("[SECURITY ERROR] FRONTEND_URL is not explicitly configured in production.")
            raise RuntimeError("FRONTEND_URL must be configured in production to restrict CORS.")
    # Run Database Migrations (Alembic Upgrade) on startup
    try:
        from alembic.config import Config
        from alembic import command
        from pathlib import Path
        
        logger.info("Running database migrations on startup...")
        base_dir = Path(__file__).resolve().parent.parent
        ini_path = base_dir / "alembic.ini"
        if not ini_path.exists():
            ini_path = base_dir.parent / "backend" / "alembic.ini"
            
        if ini_path.exists():
            alembic_cfg = Config(str(ini_path))
            script_location = base_dir / "alembic"
            if not script_location.exists():
                script_location = base_dir.parent / "backend" / "alembic"
            alembic_cfg.set_main_option("script_location", str(script_location))
            
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            logger.info("Database migrations completed successfully.")
        else:
            logger.warning(f"alembic.ini not found at {ini_path}, falling back to metadata.create_all")
            from app.db.database import engine, Base
            import app.db.models  # noqa: F401
            await asyncio.to_thread(Base.metadata.create_all, bind=engine)
    except Exception as e:
        logger.error(f"Error running database migrations: {e}", exc_info=True)
        try:
            from app.db.database import engine, Base
            import app.db.models  # noqa: F401
            await asyncio.to_thread(Base.metadata.create_all, bind=engine)
            logger.info("Database tables created via create_all fallback.")
        except Exception as ex:
            logger.error(f"Metadata create_all fallback failed: {ex}", exc_info=True)

    # Model Health Validation: log artifact presence only — no warmup to save RAM
    try:
        from pathlib import Path
        lstm_path = Path(__file__).resolve().parent.parent.parent / "ml" / "artifacts" / "best_lstm.pt"
        if lstm_path.exists():
            logger.info("[MODEL HEALTH] best_lstm.pt found on disk.")
        else:
            logger.warning(
                "[MODEL HEALTH] best_lstm.pt not found — will fall back to mean-reversion on forecast requests."
            )
    except Exception as e:
        logger.warning(f"Model validation check bypassed: {e}")

    # Check if database is empty and requires seeding
    is_empty_db = False
    try:
        db = SessionLocal()
        from app.db.models import Asset
        asset_count = db.query(Asset).count()
        db.close()
        logger.info(f"[Lifespan] Current database asset count: {asset_count}")
        if asset_count == 0:
            is_empty_db = True
    except Exception as e:
        logger.error(f"[Lifespan] Error checking database asset count: {e}", exc_info=True)
        is_empty_db = True

    if is_empty_db:
        logger.info("[Lifespan] Empty database detected. Initiating background self-seeding...")
        asyncio.create_task(run_database_seeder())

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
    from concurrent.futures import ThreadPoolExecutor
    scheduler = AsyncIOScheduler()
    bg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bg_tasks")
    
    async def scheduled_refresh_job():
        """Scheduled hourly refresh executed by APScheduler."""
        logger.info("[Scheduler] Auto-running hourly full data refresh...")
        try:
            db = SessionLocal()
            
            # 1a. Enrich Asset Metadata
            if not enrich_assets_lock.locked():
                try:
                    async with enrich_assets_lock:
                        # Wrap sync block in a timeout to prevent scheduler backlog using dedicated executor
                        await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(bg_executor, enrich_assets), timeout=1800)
                except asyncio.TimeoutError:
                    logger.error("[Scheduler] Asset enrichment timed out after 30 minutes.")
                except Exception as e:
                    logger.error(f"[Scheduler] Asset enrichment error: {e}", exc_info=True)
            else:
                logger.warning("[Scheduler] Asset enrichment skipped as previous run is still executing.")
            
            # 1b. Refresh live technicals
            try:
                await asyncio.get_event_loop().run_in_executor(bg_executor, refresh_live_technicals, db)
            except Exception as e:
                logger.error(f"[Scheduler] Technicals error: {e}", exc_info=True)
            
            # 1c. Run flagship ML inference pipeline
            try:
                from ml.pipelines.inference_pipeline import run_inference
                logger.info("[Scheduler] Executing flagship ML inference pipeline...")
                await asyncio.get_event_loop().run_in_executor(bg_executor, run_inference)
            except Exception as e:
                logger.error(f"[Scheduler] Inference error: {e}", exc_info=True)
            
            # 2. Pre-compute heavy correlation matrices
            try:
                from app.api.routes.correlations import precompute_correlations_sync
                logger.info("[Scheduler] Pre-computing correlation matrices...")
                await asyncio.get_event_loop().run_in_executor(bg_executor, precompute_correlations_sync, db)
            except Exception as e:
                logger.error(f"[Scheduler] Correlation pre-compute error: {e}", exc_info=True)
                
            # 3. Clear response cache (this clears any standard API responses, but we seeded the correlation cache directly)
            try:
                _cache.clear()
                # Re-seed the correlations after clear
                await asyncio.to_thread(precompute_correlations_sync, db)
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

            # 3c. Run autonomous paper trading cycle
            try:
                from app.services.trading_agent import run_autonomous_trading_cycle
                logger.info("[Scheduler] Executing autonomous paper trading cycle...")
                await asyncio.get_event_loop().run_in_executor(bg_executor, run_autonomous_trading_cycle)
            except Exception as e:
                logger.error(f"[Scheduler] Trading cycle error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[Scheduler] Database session error: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    # Schedule the refresh job to run every hour
    scheduler.add_job(scheduled_refresh_job, 'interval', hours=1, max_instances=1)
    scheduler.start()

    # Trigger an initial run immediately if not in testing mode
    if os.getenv("TESTING") != "True":
        logger.info("[Lifespan] Triggering initial data refresh, inference, and trading cycle immediately on startup...")
        asyncio.create_task(scheduled_refresh_job())

    # Start WebSocket tasks
    # On Render (or LOW_MEM), Binance WS is geo-blocked (HTTP 451).
    # Skip it entirely and rely on the REST-polling fallback inside the price endpoint.
    low_mem = os.getenv("LOW_MEM") == "true" or os.getenv("RENDER") == "true"
    if low_mem:
        logger.warning("[Lifespan] LOW_MEM/RENDER mode: Binance WebSocket disabled. Using REST polling fallback.")
        binance_task = asyncio.create_task(asyncio.sleep(0))  # no-op
    else:
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
    title="Crypto Ensemble Forecaster API",
    description="Machine Learning financial forecasting platform",
    version="1.0.0",
    lifespan=lifespan
)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

insecure_cors = os.environ.get("INSECURE_DEV_CORS", "false").lower() == "true"
frontend_origin = os.getenv("FRONTEND_URL") or get_setting("FRONTEND_URL")

if insecure_cors:
    dynamic_origins = ["*"]
else:
    if frontend_origin:
        dynamic_origins = [origin.strip().rstrip("/") for origin in frontend_origin.split(",") if origin.strip()]
        if "http://localhost:3000" not in dynamic_origins:
            dynamic_origins.append("http://localhost:3000")
    else:
        dynamic_origins = ["*"]

# Initialize CORS Middleware at module creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=dynamic_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
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
app.include_router(auth.router,        prefix="/api/v1")
app.include_router(assets.router,      prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(graph.router,       prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(explain.router,     prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(forecast.router,    prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(status.router,      prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(coins.router,       prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(performance.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(correlations.router,prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(sentiment_data.router,prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(screener.router,    prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(app_settings_route.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(portfolio.router,   prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(stream.router,      prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(risk.router,        prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(scheduler.router,   prefix="/api/v1", dependencies=[Depends(verify_api_key)])
from app.api.routes import backtest
app.include_router(backtest.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

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


from fastapi import HTTPException

@app.get("/readiness")
async def readiness():
    """Readiness check endpoint verifying database and Redis connectivity."""
    from datetime import datetime, timezone
    from sqlalchemy import text
    from app.core.cache import redis_client
    
    db_status = "healthy"
    redis_status = "healthy"
    
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        logger.error(f"Readiness DB health check failed: {e}")
        db_status = "unhealthy"
        
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            if redis_client:
                redis_client.ping()
            else:
                redis_status = "unhealthy"
        except Exception as e:
            logger.error(f"Readiness Redis health check failed: {e}")
            redis_status = "unhealthy"
    else:
        redis_status = "disabled"
        
    if db_status == "unhealthy" or redis_status == "unhealthy":
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "db": db_status,
                "redis": redis_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
    return {
        "status": "ready",
        "db": db_status,
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

