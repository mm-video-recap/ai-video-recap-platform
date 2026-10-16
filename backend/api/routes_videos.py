"""
Video routes: upload (multipart "file"), list, detail, delete.

NOTE: no `from __future__ import annotations` in this module — FastAPI must
resolve the `UploadFile` annotation at route-registration time.
"""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from backend.agents.agent01_ingestion import IngestionAgent, persist_ingestion
from backend.api.deps import check_fair_use, get_current_user, log_event
from backend.api.schemas import UploadResponse, VideoDetail, VideoSummary
from backend.celery_app import PRIORITY_HIGH, PRIORITY_NORMAL
from backend.config import get_settings
from backend.database import Job, User, Video, get_db
from backend.api.rate_limit import limiter

log = logging.getLogger("api.videos")

router = APIRouter(prefix="/api/videos", tags=["videos"])


def _latest_job_dict(db: Session, video_id: str) -> dict | None:
    job = (db.query(Job).filter_by(video_id=video_id)
           .order_by(Job.created_at.desc()).first())
    if not job:
        return None
    return {"id": job.id, "status": job.status, "stage": job.stage,
            "progress": job.progress}


def _to_summary(db: Session, video: Video) -> VideoSummary:
    latest = _latest_job_dict(db, video.id)
    return VideoSummary(
        id=video.id, original_name=video.original_name, container=video.container,
        duration_sec=video.duration_sec, size_bytes=video.size_bytes,
        created_at=video.created_at.isoformat(),
        latest_job=latest,
        title=video.original_name or "Untitled video",
        status=(latest or {}).get("status") or "uploaded",
        thumbnail_url=None)  # thumbnails are generated on disk during processing; no public URL yet


@router.post("/upload", response_model=UploadResponse,
             status_code=status.HTTP_201_CREATED)
# Upload cap from settings (RATE_LIMIT_UPLOAD, default "10/minute") — the
# setting used to be ignored because the value was hardcoded here.
@limiter.limit(get_settings().RATE_LIMIT_UPLOAD)
def upload_video(request: Request, file: UploadFile = File(...),
                 output_lang: str = Query(default="en", pattern="^(en|my)$"),
                 subtitle_language: str = Query(default="my",
                                               pattern="^(my|en|none)$"),
                 recap_style: str = Query(default="detailed",
                                          pattern="^(concise|detailed|highlights)$"),
                 intro_enabled: bool = Query(default=True),
                 outro_enabled: bool = Query(default=True),
                 transcription_provider: str = Query(default="auto",
                                                     pattern="^(auto|gemini|groq)$"),
                 # Per-user (BYOK) transcription key: a FORM field, never a
                 # query param — query strings land in access logs.
                 transcription_key: str = Form(default=""),
                 # Voiceover: "original" keeps the source audio; "tts"
                 # replaces it with synthesized narration of the recap.
                 voice_mode: str = Query(default="original",
                                         pattern="^(original|tts)$"),
                 tts_provider: str = Query(default="edge",
                                           pattern="^(edge|gemini)$"),
                 tts_voice: str = Query(default="thiha"),
                 tts_rate: float = Query(default=1.0, ge=0.5, le=2.0),
                 tts_pitch: int = Query(default=0, ge=-20, le=20),
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    settings = get_settings()

    # fair-use gate BEFORE we touch disk (estimate from filename-unknown duration)
    check_fair_use(db, user, settings, estimated_seconds=600)

    # B19 — early size cap: reject oversized uploads BEFORE writing the
    # whole file to disk. Content-Length first (no body read at all), then
    # a running byte count while streaming (covers chunked/no-length bodies).
    max_bytes = settings.MAX_UPLOAD_BYTES
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload too large: Content-Length exceeds "
                           f"{max_bytes} bytes free-tier limit")
        except ValueError:
            pass  # unparseable header — fall through to the streaming count

    suffix = Path(file.filename or "upload.bin").suffix.lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin")
    try:
        written = 0
        while chunk := file.file.read(4 * 1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload too large: exceeds {max_bytes} bytes "
                           f"free-tier limit")
            tmp.write(chunk)
    except Exception:
        # Streaming aborted (413 or I/O error): close + delete the partial
        # temp file so a rejected upload leaves nothing on disk.
        try:
            tmp.close()
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        raise
    else:
        tmp.close()
    tmp_path = Path(tmp.name)

    try:
        agent = IngestionAgent(max_bytes=settings.MAX_UPLOAD_BYTES,
                               max_duration_sec=settings.MAX_VIDEO_DURATION_SEC)
        result = agent.ingest(tmp_path, file.filename or "upload", user.id)
        if not result.ok:
            raise HTTPException(status_code=400, detail="; ".join(result.errors))

        duration = (result.metadata.get("duration_sec") or 600)
        # re-check fair use with the real duration now that we know it
        check_fair_use(db, user, settings, estimated_seconds=float(duration))

        from backend.storage import get_storage  # noqa: PLC0415
        storage = get_storage()
        ext = suffix if suffix else f".{result.container or 'mp4'}"
        storage_key = f"uploads/{result.video_id}/original{ext}"
        storage.put(tmp_path, storage_key)
        stored_path = storage_key if storage.name != "local" else str(
            storage.absolute(storage_key))  # type: ignore[attr-defined]

        # Per-user transcription key: encrypt at rest (Fernet) before it
        # touches the DB. Refuse outright when the server has no
        # USER_KEY_ENCRYPTION_KEY — never store a plaintext key.
        transcription_key_enc = ""
        if transcription_key:
            from backend.security.keyvault import encrypt_key  # noqa: PLC0415
            try:
                transcription_key_enc = encrypt_key(transcription_key)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        # TTS narration prefs: validate the voice now (400) rather than
        # silently falling back to original audio at render time.
        if voice_mode == "tts":
            from backend.agents.agent_tts import validate_tts_prefs  # noqa: PLC0415
            try:
                validate_tts_prefs(tts_provider, tts_voice, tts_rate, tts_pitch)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        video, job = persist_ingestion(
            db, result, user_id=user.id, storage_path=stored_path,
            output_lang=output_lang,
            subtitle_language=subtitle_language,
            recap_style=recap_style,
            intro_enabled=intro_enabled,
            outro_enabled=outro_enabled,
            transcription_provider=transcription_provider,
            transcription_key_enc=transcription_key_enc,
            voice_mode=voice_mode,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            tts_rate=tts_rate,
            tts_pitch=tts_pitch,
            priority=PRIORITY_HIGH if user.is_admin else PRIORITY_NORMAL)
        db.commit()
        log_event(db, user.id, "video_uploaded",
                  video_id=video.id, job_id=job.id, duration_sec=duration)

        # hand off to the celery pipeline (broker may be down -> stays queued)
        from backend.celery_app.tasks import enqueue_pipeline  # noqa: PLC0415
        enqueue_pipeline(video.id, job.id, priority=job.priority)

        estimated = max(60, int(float(duration) * 0.6) + 60)
        return UploadResponse(video_id=video.id, job_id=job.id,
                              estimated_seconds=estimated)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("", response_model=list[VideoSummary])
def list_videos(all: int = Query(default=0),
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    q = db.query(Video).order_by(Video.created_at.desc())
    if not (all and user.is_admin):
        q = q.filter_by(user_id=user.id)
    return [_to_summary(db, v) for v in q.limit(200).all()]


@router.get("/{video_id}", response_model=VideoDetail)
def get_video(video_id: str, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    video = db.query(Video).filter_by(id=video_id).one_or_none()
    if video is None or (video.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Video not found")
    summary = _to_summary(db, video)
    return VideoDetail(**summary.model_dump(), width=video.width,
                       height=video.height, sha256_prefix=video.sha256_prefix)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    video = db.query(Video).filter_by(id=video_id).one_or_none()
    if video is None or (video.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Video not found")
    # best-effort file cleanup
    # NOTE: processing/ artifacts are keyed by JOB id, the other buckets by
    # VIDEO id — delete both, or orphaned frames/audio pile up.
    try:
        from backend.storage import get_storage  # noqa: PLC0415
        storage = get_storage()
        jobs = db.query(Job).filter_by(video_id=video_id).all()
        keys = [f"{prefix}/{video.id}"
                for prefix in ("uploads", "results", "thumbnails")]
        # Render outputs are keyed by JOB id, not video id.
        keys += [f"{prefix}/{j.id}"
                 for j in jobs for prefix in ("results", "thumbnails")]
        keys += [f"processing/{j.id}" for j in jobs]
        for key in keys:
            try:
                if hasattr(storage, "absolute"):
                    import shutil  # noqa: PLC0415
                    p = storage.absolute(key)  # type: ignore[attr-defined]
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    elif p.is_file():
                        p.unlink(missing_ok=True)
                else:
                    storage.delete(key)
            except Exception:
                pass
    except Exception as exc:
        log.warning("storage cleanup failed for video %s: %s", video_id, exc)
    for job in db.query(Job).filter_by(video_id=video_id).all():
        # Outputs have a NOT NULL job_id FK with no delete cascade:
        # deleting the Job first would null them and raise IntegrityError.
        from backend.database import Output  # noqa: PLC0415
        db.query(Output).filter_by(job_id=job.id).delete(synchronize_session=False)
        db.delete(job)
    db.delete(video)
    db.commit()
    log_event(db, user.id, "video_deleted", video_id=video_id)
    return None
