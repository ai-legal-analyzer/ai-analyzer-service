from celery import Celery
from app.config import settings

celery_app = Celery(
    "ai_analyzer_service",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    broker_connection_retry_on_startup=True,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000
)

celery_app.conf.task_routes = {
    "app.tasks.analyze_chunks": {"queue": 'chunk_processing'},
    "app.tasks.*": {"queue": 'default'}
}
