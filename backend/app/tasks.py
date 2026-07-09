import logging
from app.core.celery_app import celery_app

logger = logging.getLogger("cryptograph.tasks")

@celery_app.task(name="app.tasks.run_inference_pipeline_task")
def run_inference_pipeline_task():
    """Celery task to run technical feature calculations and ML inference."""
    from datetime import datetime, timezone
    from app.db.database import SessionLocal
    from app.db.models import AppSetting
    from app.api.routes.screener import refresh_live_technicals
    from ml.pipelines.inference_pipeline import main as run_inference_main
    from app.core.streams.binance_ws import refresh_predictions_in_ssot

    logger.info("Starting inference pipeline via Celery task...")
    db = SessionLocal()
    lock_key = "inference_trigger_lock"
    try:
        # DB-level locking
        lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).with_for_update().first()
        now_ts = datetime.now(timezone.utc).timestamp()
        if lock_setting:
            try:
                if now_ts - float(lock_setting.setting_value) < 300:
                    logger.info("Inference already running (DB lock held). Skipping.")
                    return {"status": "skipped", "reason": "lock_held"}
            except Exception:
                pass
            lock_setting.setting_value = str(now_ts)
        else:
            lock_setting = AppSetting(setting_key=lock_key, setting_value=str(now_ts))
            db.add(lock_setting)
        db.commit()

        # Step 1: Refresh Technicals
        logger.info("Refreshing live technicals...")
        refresh_live_technicals(db=db)

        # Step 2: Run Inference
        logger.info("Executing flagship ML inference pipeline...")
        run_inference_main()

        # Step 3: Refresh SSOT Pred Cache
        logger.info("Refreshing predictions in SSOT...")
        refresh_predictions_in_ssot(db)

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Inference task error: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).first()
            if lock_setting:
                lock_setting.setting_value = "0"
                db.commit()
        except Exception:
            pass
        db.close()


@celery_app.task(name="app.tasks.run_scheduler_pipeline_task")
def run_scheduler_pipeline_task():
    """Celery task to run full live data sync, ML models, and trading agents."""
    from datetime import datetime, timezone
    from app.db.database import SessionLocal
    from app.db.models import AppSetting
    from app.core.state import scheduler_state
    
    start_time = datetime.now(timezone.utc)
    logger.info("Starting scheduler pipeline via Celery task...")
    
    db = SessionLocal()
    lock_key = "scheduler_lock"
    try:
        lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).with_for_update().first()
        now_ts = start_time.timestamp()
        
        if lock_setting:
            try:
                last_lock_time = float(lock_setting.setting_value)
                if now_ts - last_lock_time < 900:
                    logger.info("Another scheduler instance is running. Skipping.")
                    return {"status": "skipped", "reason": "lock_held"}
            except Exception:
                pass
            lock_setting.setting_value = str(now_ts)
        else:
            lock_setting = AppSetting(setting_key=lock_key, setting_value=str(now_ts))
            db.add(lock_setting)
            
        db.commit()
    except Exception as e:
        logger.error(f"Failed to acquire DB lock for scheduler: {e}")
        db.close()
        return {"status": "failed", "error": "db_lock_failed"}
        
    scheduler_state.is_running = True
    scheduler_state.status = "running"
    try:
        from ml.pipelines.inference_pipeline import run_inference
        from app.services.trading_agent import run_autonomous_trading_cycle
        from app.core.streams.binance_ws import refresh_predictions_in_ssot
        from app.api.routes.graph import _compute_correlation_graph

        # Step 1: Run Inference
        logger.info("Running inference...")
        inf_result = run_inference()

        # Step 2: SSOT Refresh
        logger.info("Refreshing SSOT prediction cache...")
        refresh_predictions_in_ssot(db)

        # Step 3: Trading Swarm
        logger.info("Running autonomous trading cycle...")
        trade_result = run_autonomous_trading_cycle()

        # Step 4: Precompute Graph Snapshot
        logger.info("Precomputing correlation graph...")
        _compute_correlation_graph(db, 100, "live")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        scheduler_state.last_run = end_time.isoformat()
        scheduler_state.last_duration_sec = round(duration, 2)
        scheduler_state.last_result = {
            "inference": inf_result,
            "trading": trade_result
        }
        scheduler_state.status = "success"
        scheduler_state.is_running = False
        return {"status": "success", "duration_sec": duration}
    except Exception as e:
        logger.error(f"Scheduler pipeline run failed: {e}", exc_info=True)
        scheduler_state.status = f"error: {str(e)}"
        scheduler_state.is_running = False
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            lock_setting = db.query(AppSetting).filter_by(setting_key=lock_key).first()
            if lock_setting:
                lock_setting.setting_value = "0"
                db.commit()
        except Exception:
            pass
        db.close()
