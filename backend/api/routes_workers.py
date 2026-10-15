"""
Community worker gateway.

Workers register with a shared gateway token (WORKER_GATEWAY_TOKEN env),
heartbeat to stay online, and pull the next queued task.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.api.schemas import WorkerRegisterIn, WorkerRegisterOut
from backend.config import get_settings
from backend.database import CommunityWorker, Job, Video, get_db

log = logging.getLogger("api.workers")

router = APIRouter(prefix="/api/workers", tags=["workers"])


def _check_gateway(x_worker_token: str | None = Header(default=None)) -> None:
    expected = (get_settings().WORKER_GATEWAY_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=503,
                            detail="Worker gateway is disabled (no WORKER_GATEWAY_TOKEN)")
    if x_worker_token != expected:
        raise HTTPException(status_code=401, detail="Invalid worker token")


@router.post("/register", response_model=WorkerRegisterOut)
def register_worker(body: WorkerRegisterIn, db: Session = Depends(get_db),
                    _gate: None = Depends(_check_gateway)):
    worker = CommunityWorker(name=body.name, worker_type=body.worker_type,
                             capabilities=body.capabilities, status="online",
                             last_heartbeat=datetime.now(timezone.utc))
    db.add(worker)
    db.commit()
    db.refresh(worker)
    log.info("worker registered: %s (%s)", worker.id, body.name)
    return WorkerRegisterOut(worker_id=worker.id)


@router.post("/{worker_id}/heartbeat")
def heartbeat(worker_id: str, db: Session = Depends(get_db),
              _gate: None = Depends(_check_gateway)):
    worker = db.query(CommunityWorker).filter_by(id=worker_id).one_or_none()
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.last_heartbeat = datetime.now(timezone.utc)
    worker.status = "online"
    db.commit()
    return {"ok": True}


@router.get("/tasks/next")
def next_task(db: Session = Depends(get_db),
              _gate: None = Depends(_check_gateway)):
    job = (db.query(Job).filter_by(status="queued")
           .order_by(Job.priority.desc(), Job.created_at.asc()).first())
    if job is None:
        return {"task": None}
    video = db.query(Video).filter_by(id=job.video_id).one_or_none()
    return {"task": {
        "job_id": job.id,
        "video_id": job.video_id,
        "stage": job.stage,
        "priority": job.priority,
        "storage_path": video.storage_path if video else None,
        "output_lang": job.output_lang,
    }}
