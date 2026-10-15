"""
Celery application for the AI Video Recap Platform.

5 queues (per spec):
  video_upload_queue | video_processing_queue | ai_analysis_queue |
  render_queue | email_queue

Priority routing: free user = normal (3), admin = high (9), emergency = 9.
Redis broker priorities 0-9 are honored by the Redis transport.

Beat schedule:
  health_check_providers -> every 5 minutes
  cleanup_old_files      -> daily
"""
from __future__ import annotations

from celery import Celery
from kombu import Queue

from backend.config import get_settings

settings = get_settings()

QUEUE_NAMES = (
    "video_upload_queue",
    "video_processing_queue",
    "ai_analysis_queue",
    "render_queue",
    "email_queue",
)

# priority levels
PRIORITY_NORMAL = 3   # free users
PRIORITY_HIGH = 9     # admin / emergency

celery_app = Celery(
    "ai_video_recap",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_queues=tuple(Queue(name, routing_key=name) for name in QUEUE_NAMES),
    task_default_queue="video_processing_queue",
    task_routes={
        "backend.celery_app.tasks.ingest_video": {"queue": "video_upload_queue"},
        "backend.celery_app.tasks.process_video": {"queue": "video_processing_queue"},
        "backend.celery_app.tasks.ai_analyze": {"queue": "ai_analysis_queue"},
        "backend.celery_app.tasks.render_recap": {"queue": "render_queue"},
        "backend.celery_app.tasks.send_notification": {"queue": "email_queue"},
        "backend.celery_app.tasks.health_check_providers": {"queue": "ai_analysis_queue"},
        "backend.celery_app.tasks.cleanup_old_files": {"queue": "video_processing_queue"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SEC,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SEC,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=False,
    beat_schedule={
        "health-check-providers": {
            "task": "backend.celery_app.tasks.health_check_providers",
            "schedule": float(settings.PROVIDER_HEALTH_CHECK_SECONDS),
        },
        "cleanup-old-files": {
            "task": "backend.celery_app.tasks.cleanup_old_files",
            "schedule": 86400.0,  # daily
        },
    },
    timezone="UTC",
    enable_utc=True,
)

# Import tasks so they register on the app. Keep this import last and lazy-safe:
# tasks.py imports agents lazily inside task bodies.
from backend.celery_app import tasks as _tasks  # noqa: E402,F401  (registers tasks)

__all__ = ["celery_app", "QUEUE_NAMES", "PRIORITY_NORMAL", "PRIORITY_HIGH"]
