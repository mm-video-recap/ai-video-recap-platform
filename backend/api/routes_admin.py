"""
Admin routes (is_admin only): overview, jobs, providers, feedback,
analytics, errors.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.deps import require_admin
from backend.config import get_settings
from backend.database import (
    AnalyticsEvent,
    ApiUsage,
    ErrorLog,
    Feedback,
    Job,
    ProviderHealth,
    User,
    Video,
    get_db,
)

log = logging.getLogger("api.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _queue_depth() -> dict:
    """Best-effort queue depth via celery inspect; 0s when broker is down."""
    depth = {q: 0 for q in ("video_upload_queue", "video_processing_queue",
                            "ai_analysis_queue", "render_queue", "email_queue")}
    try:
        from backend.celery_app import celery_app  # noqa: PLC0415
        insp = celery_app.control.inspect(timeout=3)
        for pool in (insp.active() or {}).values():
            for t in pool:
                q = (t.get("delivery_info") or {}).get("routing_key")
                if q in depth:
                    depth[q] += 1
        for pool in (insp.reserved() or {}).values():
            for t in pool:
                q = (t.get("delivery_info") or {}).get("routing_key")
                if q in depth:
                    depth[q] += 1
    except Exception as exc:
        log.debug("celery inspect failed: %s", exc)
    return depth


@router.get("/overview")
def overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings = get_settings()
    active_statuses = ("queued", "processing", "analyzing", "rendering")
    providers = [
        {"name": p.provider, "status": p.status, "latency_ms": p.latency_ms,
         "error_rate": p.error_rate, "checked_at": p.checked_at.isoformat()
         if p.checked_at else None}
        for p in db.query(ProviderHealth).all()
    ]
    depths = _queue_depth()
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "jobs_active": db.query(func.count(Job.id)).filter(
            Job.status.in_(active_statuses)).scalar(),
        "queue_depth": sum(depths.values()),
        "queue_depths": depths,
        "providers": providers,
        # NOTE: the absolute STORAGE_ROOT path is deliberately NOT exposed —
        # it is server-internal (and differs per host). Only the provider
        # name is needed by the admin UI.
        "storage": {"provider": (settings.STORAGE_PROVIDER or "local")},
    }


@router.get("/jobs")
def admin_jobs(status: str | None = Query(default=None),
               limit: int = Query(default=50, le=200),
               admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    q = db.query(Job).order_by(Job.created_at.desc())
    if status:
        q = q.filter_by(status=status)
    return [{"id": j.id, "video_id": j.video_id, "user_id": j.user_id,
             "status": j.status, "stage": j.stage, "progress": j.progress,
             "error": j.error, "created_at": j.created_at.isoformat()}
            for j in q.limit(limit).all()]


@router.get("/providers")
def admin_providers(admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    return [{"provider": p.provider, "status": p.status,
             "latency_ms": p.latency_ms, "error_rate": p.error_rate,
             "last_error": p.last_error,
             "checked_at": p.checked_at.isoformat() if p.checked_at else None}
            for p in db.query(ProviderHealth).all()]


@router.get("/feedback")
def admin_feedback(limit: int = Query(default=50, le=200),
                   admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    rows = (db.query(Feedback).order_by(Feedback.created_at.desc())
            .limit(limit).all())
    return [{"id": f.id, "user_id": f.user_id, "job_id": f.job_id,
             "rating": f.rating, "comment": f.comment,
             "created_at": f.created_at.isoformat()} for f in rows]


@router.get("/analytics")
def analytics(admin: User = Depends(require_admin),
              db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    daily_users = (db.query(func.count(func.distinct(AnalyticsEvent.user_id)))
                   .filter(AnalyticsEvent.created_at >= day_ago).scalar())
    processing_volume_sec = (db.query(func.coalesce(func.sum(Video.duration_sec), 0))
                             .filter(Video.created_at >= week_ago).scalar()) or 0
    ai_rows = (db.query(ApiUsage.provider, func.count(ApiUsage.id))
               .filter(ApiUsage.created_at >= week_ago)
               .group_by(ApiUsage.provider).all())
    errors = (db.query(func.count(ErrorLog.id))
              .filter(ErrorLog.created_at >= day_ago).scalar())
    return {
        "daily_users": daily_users,
        "processing_volume": {"seconds_last_7d": round(float(processing_volume_sec), 1)},
        "ai_usage": {provider: count for provider, count in ai_rows},
        "errors": {"last_24h": errors},
    }


@router.get("/errors")
def admin_errors(limit: int = Query(default=50, le=200),
                 admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    rows = (db.query(ErrorLog).order_by(ErrorLog.created_at.desc())
            .limit(limit).all())
    return [{"id": e.id, "job_id": e.job_id, "user_id": e.user_id,
             "source": e.source, "message": e.message,
             "created_at": e.created_at.isoformat()} for e in rows]
