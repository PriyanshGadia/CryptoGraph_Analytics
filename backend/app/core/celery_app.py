import os
import logging
from celery import Celery

logger = logging.getLogger("cryptograph.celery")

# Read Redis broker/backend URL from environment, default to None (eager mode)
broker_url = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND") or broker_url

celery_app = Celery(
    "cryptograph",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Set to eager execution if there is no running Redis broker (graceful fallback)
if not broker_url:
    logger.warning("No broker URL (CELERY_BROKER_URL/REDIS_URL) defined. Celery will execute tasks synchronously (eager mode).")
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True
    )
else:
    logger.info(f"Celery initialized with broker: {broker_url}")
