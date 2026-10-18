"""
Result routes: recap payload + file download.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user
from backend.api.schemas import (
    HighlightItem,
    ResultsResponse,
    TimelineItem,
    TranscriptItem,
)
from backend.database import Job, Output, User, get_db

log = logging.getLogger("api.results")

router = APIRouter(prefix="/api/results", tags=["results"])


def _get_owned_job(db: Session, job_id: str, user: User) -> Job:
    job = db.query(Job).filter_by(id=job_id).one_or_none()
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _live_quota_flag(data: dict) -> bool:
    """Recompute quota_exhausted from the stored AI-stage outputs with
    the current logic (local import: keeps this module importable
    without the celery task graph)."""
    from backend.celery_app.tasks import _job_hit_quota  # noqa: PLC0415
    try:
        return bool(_job_hit_quota(data or {}))
    except Exception:
        return bool((data or {}).get("quota_exhausted", False))


def _resolve_url(output: Output, job_id: str, kind: str, base_url: str) -> str | None:
    """
    Download URL for an output: cloud presigned URL or local API route.

    Local downloads are built from the INCOMING request's base URL
    (request.base_url), NOT settings.API_BASE_URL — the env default is
    http://localhost:8000, which would hand production users a localhost
    link. API_BASE_URL is only the fallback for contexts without a request
    (e.g. email links in celery tasks, where it MUST be set to the public
    backend URL — see the production-misconfig warning in main.py).
    """
    from backend.storage import get_storage  # noqa: PLC0415
    storage = get_storage()
    if storage.name == "local":
        base = base_url.rstrip("/")
        if kind == "recap_video":
            return f"{base}/api/results/{job_id}/download"
        return f"{base}/api/results/{job_id}/download?kind={kind}"
    try:
        return storage.get_url(output.storage_path)
    except Exception as exc:
        log.warning("get_url failed for %s: %s", output.storage_path, exc)
        return None


def _output_by_kind(db: Session, job_id: str, kind: str) -> Output | None:
    return (db.query(Output).filter_by(job_id=job_id, kind=kind)
            .order_by(Output.created_at.desc()).first())


def _video_output_mode(db: Session, video_id: str) -> str:
    """Output mode stored in video.meta ("recap" | "dubbing")."""
    from backend.database import Video  # noqa: PLC0415 - avoid import cycle

    video = db.query(Video).filter_by(id=video_id).one_or_none()
    mode = (video.meta or {}).get("output_mode", "recap") if video is not None else "recap"
    return mode if mode in ("recap", "dubbing") else "recap"


def _video_recap_style(db: Session, video_id: str) -> str:
    """Recap style stored in video.meta (recap mode only)."""
    from backend.database import Video  # noqa: PLC0415 - avoid import cycle

    video = db.query(Video).filter_by(id=video_id).one_or_none()
    style = (video.meta or {}).get("recap_style", "detailed") if video is not None else "detailed"
    return style if style in ("short", "detailed", "cinematic", "custom") else "detailed"


@router.get("/{job_id}", response_model=ResultsResponse)
def get_results(job_id: str, request: Request,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    job = _get_owned_job(db, job_id, user)
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Results not ready yet")

    data = job.result or {}
    summary = data.get("summary", {}) or {}
    speech = data.get("speech", {}) or {}
    video_out = _output_by_kind(db, job_id, "recap_video")
    sub_out = _output_by_kind(db, job_id, "subtitles")
    if video_out is None:
        raise HTTPException(status_code=404, detail="Recap video missing")

    base_url = str(request.base_url)
    return ResultsResponse(
        download_url=_resolve_url(video_out, job_id, "recap_video", base_url) or "",
        title=summary.get("title", "Video Recap"),
        description=summary.get("description", ""),
        summary_short=summary.get("summary_short", ""),
        summary_long=summary.get("summary_long", ""),
        key_points=[str(p) for p in summary.get("key_points", [])],
        timeline=[TimelineItem(**t) for t in summary.get("timeline", [])
                  if isinstance(t, dict) and "start" in t],
        highlights=[HighlightItem(**{k: h[k] for k in ("start", "end", "score")
                                     if k in h})
                    for h in data.get("highlights", []) if isinstance(h, dict)],
        transcript=[TranscriptItem(**{k: s[k] for k in ("start", "end", "text")
                                      if k in s})
                    for s in speech.get("transcript", []) if isinstance(s, dict)],
        subtitle_url=_resolve_url(sub_out, job_id, "subtitles", base_url) if sub_out else None,
        warnings=[str(w) for w in (data.get("render", {}) or {}).get("warnings", [])],
        # Recompute the quota flag live from the stored stage outputs
        # (not the persisted value): the 2026-10-18 fix narrowed the
        # flag to "quota actually left output incomplete", and old jobs
        # stored True from transient 429s their fallbacks absorbed.
        quota_exhausted=_live_quota_flag(data),
        output_mode=_video_output_mode(db, job.video_id),
        recap_style=_video_recap_style(db, job.video_id),
    )


@router.get("/{job_id}/download")
def download_result(job_id: str, kind: str = "recap_video",
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    job = _get_owned_job(db, job_id, user)
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Results not ready yet")
    output = _output_by_kind(db, job_id, kind)
    if output is None:
        raise HTTPException(status_code=404, detail="File not found")

    from backend.storage import get_storage  # noqa: PLC0415
    from backend.storage.local import LocalStorage  # noqa: PLC0415
    storage = get_storage()
    if isinstance(storage, LocalStorage):
        path = storage.absolute(output.storage_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File missing from storage")
        media = "video/mp4" if kind == "recap_video" else "text/plain"
        return FileResponse(path, media_type=media,
                            filename=Path(output.storage_path).name)
    # cloud backends: redirect to the presigned URL
    from fastapi.responses import RedirectResponse  # noqa: PLC0415
    url = storage.get_url(output.storage_path)
    return RedirectResponse(url)
