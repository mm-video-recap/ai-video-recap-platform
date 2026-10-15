"""Celery wiring: task names, 5 queues, beat schedule, pipeline chain."""
from backend.celery_app import QUEUE_NAMES, celery_app
from backend.celery_app.tasks import build_pipeline

TASK_NAMES = [
    "backend.celery_app.tasks.ingest_video",
    "backend.celery_app.tasks.process_video",
    "backend.celery_app.tasks.ai_analyze",
    "backend.celery_app.tasks.render_recap",
    "backend.celery_app.tasks.send_notification",
    "backend.celery_app.tasks.health_check_providers",
    "backend.celery_app.tasks.cleanup_old_files",
]


def test_five_queues_registered():
    names = {q.name for q in celery_app.conf.task_queues}
    assert names == set(QUEUE_NAMES) == {
        "video_upload_queue", "video_processing_queue", "ai_analysis_queue",
        "render_queue", "email_queue",
    }


def test_all_tasks_registered():
    for name in TASK_NAMES:
        assert name in celery_app.tasks, f"task not registered: {name}"


def test_task_routes_point_at_right_queues():
    routes = celery_app.conf.task_routes
    assert routes["backend.celery_app.tasks.ingest_video"]["queue"] == "video_upload_queue"
    assert routes["backend.celery_app.tasks.process_video"]["queue"] == "video_processing_queue"
    assert routes["backend.celery_app.tasks.ai_analyze"]["queue"] == "ai_analysis_queue"
    assert routes["backend.celery_app.tasks.render_recap"]["queue"] == "render_queue"
    assert routes["backend.celery_app.tasks.send_notification"]["queue"] == "email_queue"


def test_beat_schedule():
    beat = celery_app.conf.beat_schedule
    assert "health-check-providers" in beat
    assert beat["health-check-providers"]["schedule"] == 300.0
    assert beat["health-check-providers"]["task"] == \
        "backend.celery_app.tasks.health_check_providers"
    assert "cleanup-old-files" in beat
    assert beat["cleanup-old-files"]["schedule"] == 86400.0


def test_build_pipeline_chain_order():
    pipe = build_pipeline("vid-1", "job-1")
    names = [t.name for t in pipe.tasks]
    assert names == [
        "backend.celery_app.tasks.ingest_video",
        "backend.celery_app.tasks.process_video",
        "backend.celery_app.tasks.ai_analyze",
        "backend.celery_app.tasks.render_recap",
        "backend.celery_app.tasks.send_notification",
    ]


def test_task_retry_policy():
    t = celery_app.tasks["backend.celery_app.tasks.process_video"]
    assert t.max_retries == 2
    assert t.time_limit == 1800
