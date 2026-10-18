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


def _store_side_video(side_file, video_id: str, slot: str,
                      storage, max_bytes: int) -> str:
    """Stream an optional uploaded intro/outro video to temp, probe it
    with ffprobe, store it, return the storage key. Raises HTTPException
    400 when ffprobe exists but cannot read the file (corrupt), 413
    when it exceeds the cap. Temp file is always removed."""
    import shutil  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from backend.agents.agent01_ingestion import _ffprobe_metadata  # noqa: PLC0415

    suffix = Path(side_file.filename or f"{slot}.mp4").suffix.lower() or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        written = 0
        while chunk := side_file.file.read(4 * 1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"{slot} video too large: exceeds "
                           f"{max_bytes} bytes free-tier limit")
            tmp.write(chunk)
        tmp.close()
        tmp_path = Path(tmp.name)
        meta, used = _ffprobe_metadata(tmp_path)
        if not used and shutil.which("ffprobe"):
            raise HTTPException(
                status_code=400,
                detail=f"{slot} video appears corrupt or truncated: "
                       f"ffprobe could not read it. Re-save / re-export "
                       f"the video and upload again.")
        if used and not (meta.get("duration_sec") or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail=f"{slot} video has no readable duration.")
        key = f"uploads/{video_id}/{slot}{suffix}"
        storage.put(tmp_path, key)
        return key
    finally:
        try:
            tmp.close()
        except Exception:
            pass
        Path(tmp.name).unlink(missing_ok=True)


@router.post("/upload", response_model=UploadResponse,
             status_code=status.HTTP_201_CREATED)
# Upload cap from settings (RATE_LIMIT_UPLOAD, default "10/minute") — the
# setting used to be ignored because the value was hardcoded here.
@limiter.limit(get_settings().RATE_LIMIT_UPLOAD)
def upload_video(request: Request, file: UploadFile = File(...),
                 output_lang: str = Query(default="en", pattern="^(en|my)$"),
                 subtitle_language: str = Query(default="my",
                                               pattern="^(my|en|none)$"),
                 # Output mode: "recap" (default) builds a condensed
                 # recap from highlight clips; "dubbing" keeps the FULL
                 # original video and replaces its audio with TTS
                 # narration + translated subtitles on the original
                 # timeline. Dubbing ignores intro/outro.
                 output_mode: str = Query(default="recap",
                                          pattern="^(recap|dubbing)$"),
                 # Recap style (recap mode only; dubbing ignores it):
                 # short = key points fast, detailed = thorough story,
                 # cinematic = dramatic narration pacing,
                 # custom = user-defined length + tone.
                 recap_style: str = Query(default="detailed",
                                          pattern="^(short|detailed|cinematic|custom)$"),
                 recap_tone: str = Query(default="", max_length=200),
                 intro_enabled: bool = Query(default=True),
                 outro_enabled: bool = Query(default=True),
                 # Optional uploaded intro/outro VIDEOS (replacing the
                 # text cards): the final recap is intro video + recap
                 # clips + outro video, concatenated at render time.
                 intro_file: UploadFile = File(default=None),
                 outro_file: UploadFile = File(default=None),
                 # Per-user (BYOK) AI keys: FORM fields, never query
                 # params — query strings land in access logs. They are
                 # passed to the pipeline as task kwargs (in-memory
                 # through the broker only) and NEVER written to the
                 # database; the user's browser is the only place they
                 # are saved. When supplied, this job spends the user's
                 # own quota, never the owner's. Empty = owner keys.
                 gemini_key: str = Form(default=""),
                 groq_key: str = Form(default=""),
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

    # Key gate: only the owner account (OWNER_EMAIL) may use the server
    # (env) AI keys. Everyone else MUST bring both their own Gemini +
    # Groq keys — one each — or the upload is rejected before any file
    # is read.
    from backend.api.deps import is_owner  # noqa: PLC0415
    if not is_owner(user) and not (gemini_key and groq_key):
        raise HTTPException(
            status_code=400,
            detail="Both your own Gemini API key and Groq API key are "
                   "required. Add them in Settings → My API Keys. Only "
                   "the owner account may use the server keys.")

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

        # Optional uploaded intro/outro videos: probe + store now (a bad
        # side video fails the upload before any rows are written).
        # Ignored when the matching toggle is off.
        intro_video_key = ""
        outro_video_key = ""
        if intro_enabled and intro_file is not None and intro_file.filename:
            intro_video_key = _store_side_video(
                intro_file, result.video_id, "intro", storage, max_bytes)
        if outro_enabled and outro_file is not None and outro_file.filename:
            outro_video_key = _store_side_video(
                outro_file, result.video_id, "outro", storage, max_bytes)

        # Per-user AI keys for this job only (see the Form fields
        # above): collected here, passed to the pipeline as task kwargs,
        # never persisted. Never logged.
        user_keys: dict[str, list[str]] = {}
        if gemini_key:
            user_keys["gemini"] = [gemini_key]
        if groq_key:
            user_keys["groq"] = [groq_key]

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
            output_mode=output_mode,
            recap_style=recap_style,
            recap_tone=recap_tone,
            intro_enabled=intro_enabled,
            outro_enabled=outro_enabled,
            voice_mode=voice_mode,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            tts_rate=tts_rate,
            tts_pitch=tts_pitch,
            intro_video_key=intro_video_key,
            outro_video_key=outro_video_key,
            priority=PRIORITY_HIGH if user.is_admin else PRIORITY_NORMAL)
        db.commit()
        log_event(db, user.id, "video_uploaded",
                  video_id=video.id, job_id=job.id, duration_sec=duration)

        # hand off to the celery pipeline (broker may be down -> stays queued)
        from backend.celery_app.tasks import enqueue_pipeline  # noqa: PLC0415
        enqueue_pipeline(video.id, job.id, priority=job.priority,
                         user_keys=user_keys or None)

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
