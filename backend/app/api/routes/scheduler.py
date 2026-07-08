"""
Scheduler & Pipeline Live Sync Endpoints
"""
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from app.api.routes.forecast import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

from app.core.state import scheduler_state


@router.post("/run")
@limiter.limit("1/minute")
async def trigger_scheduler_run(request: Request, background_tasks: BackgroundTasks):
    """
    Trigger manual on-demand execution of the ML inference pipeline and portfolio swarm.
    """
    if scheduler_state.is_running:
        raise HTTPException(status_code=400, detail="Pipeline is already running")

    from app.tasks import run_scheduler_pipeline_task
    from app.core.celery_app import celery_app
    
    if celery_app.conf.task_always_eager:
        # Fallback to FastAPI BackgroundTasks to prevent blocking the HTTP response
        background_tasks.add_task(run_scheduler_pipeline_task)
        return {
            "status": "started",
            "message": "ML Pipeline & Live Data Sync triggered in background (eager fallback)",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Trigger Celery worker task asynchronously
        run_scheduler_pipeline_task.delay()
        return {
            "status": "started",
            "message": "ML Pipeline & Live Data Sync task sent to Celery queue",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/status")
def get_scheduler_status():
    """
    Get current pipeline scheduler execution status.
    """
    return {
        "status": scheduler_state.status,
        "last_run": scheduler_state.last_run,
        "last_duration_sec": scheduler_state.last_duration_sec,
        "last_result": scheduler_state.last_result,
        "is_running": scheduler_state.is_running
    }
