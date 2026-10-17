"""
Job routes: status + SSE progress stream.

SSE uses ?token=<jwt> because EventSource cannot set Authorization headers.
Progress comes from Redis pub/sub when available, otherwise the endpoint
polls the Job row — both paths emit the same {stage, progress, message}
events.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, verify_query_token
from backend.api.schemas import JobStatus
from backend.celery_app.progress import (
    close_subscriber,
    drain_subscriber,
    open_subscriber,
)
from backend.config import get_settings
from backend.database import Job, User, get_db

log = logging.getLogger("api.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL = {"completed", "failed"}

_STAGE_MESSAGES = {
    "ingesting": "Validating upload…",
    "ingested": "Upload validated",
    "processing": "Normalizing video…",
    "processed": "Video processed",
    "transcribing": "Transcribing speech…",
    "vision": "Analyzing visuals…",
    "summarizing": "Writing recap…",
    "highlights": "Picking highlights…",
    "analyzed": "Analysis complete",
    "rendering": "Rendering recap video…",
    "rendered": "Recap video ready",
    "notifying": "Sending notification…",
    "done": "Recap ready!",
}


def _get_owned_job(db: Session, job_id: str, user: User) -> Job:
    job = db.query(Job).filter_by(id=job_id).one_or_none()
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}", response_model=JobStatus)
def get_job(job_id: str, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    job = _get_owned_job(db, job_id, user)
    return JobStatus(id=job.id, status=job.status, stage=job.stage,
                     progress=job.progress, error=job.error,
                     subtitle_language=job.subtitle_language)


@router.get("/{job_id}/stream")
def stream_job(job_id: str, request: Request, token: str = Query(...),
               db: Session = Depends(get_db)):
    settings = get_settings()
    auth_user = verify_query_token(token, settings)
    is_admin = auth_user.is_admin or (auth_user.email or "").lower() in settings.admin_email_set

    job = db.query(Job).filter_by(id=job_id).one_or_none()
    if job is None or (job.user_id != auth_user.id and not is_admin):
        raise HTTPException(status_code=404, detail="Job not found")

    def event(data: dict) -> str:
        return f"event: progress\ndata: {json.dumps(data)}\n\n"

    async def gen():
        last = (None, None, None)
        # 1) current state immediately
        current = db.query(Job).filter_by(id=job_id).one_or_none()
        if current:
            payload = {"stage": current.stage, "progress": current.progress,
                       "message": _STAGE_MESSAGES.get(current.stage or "",
                                                     current.stage or ""),
                       "status": current.status}
            yield event(payload)
            last = (current.stage, current.progress, current.status)
            if current.status in TERMINAL:
                return

        # 2) DB polling + non-blocking Redis drain, up to ~115s
        sub = open_subscriber(job_id)
        deadline = time.monotonic() + 115.0
        try:
            while time.monotonic() < deadline:
                if await request.is_disconnected():
                    return
                if sub is not None:
                    for payload in drain_subscriber(sub):
                        yield event({"stage": payload.get("stage"),
                                     "progress": payload.get("progress", 0),
                                     "message": payload.get("message", ""),
                                     "status": payload.get("status")})
                        if payload.get("status") in TERMINAL:
                            return
                await asyncio.sleep(1.0)
                # expire the session so we re-read fresh state
                db.expire_all()
                current = db.query(Job).filter_by(id=job_id).one_or_none()
                if current is None:
                    yield event({"stage": "gone", "progress": 0,
                                 "message": "Job disappeared", "status": "failed"})
                    return
                key = (current.stage, current.progress, current.status)
                if key != last:
                    last = key
                    yield event({"stage": current.stage, "progress": current.progress,
                                 "message": _STAGE_MESSAGES.get(current.stage or "",
                                                                 current.stage or ""),
                                 "status": current.status})
                if current.status in TERMINAL:
                    return
        finally:
            if sub is not None:
                close_subscriber(sub)
        # keep-alive timeout reached without terminal state
        yield "event: timeout\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
