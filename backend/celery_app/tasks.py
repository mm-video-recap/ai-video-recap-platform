"""
Celery tasks for the recap pipeline.

Pipeline: ingest_video -> process_video -> ai_analyze -> render_recap
          -> send_notification
Beat:     health_check_providers (5 min), cleanup_old_files (daily)

Conventions:
- bind=True everywhere; manual retry with exponential backoff for transient
  errors (self.retry(countdown=60 * 2**retries)).
- Permanent failures: mark Job failed, write ErrorLog, notify admins.
- Progress: set_job_progress() -> Job row + Redis pub/sub.
- Heavy imports (agents, providers) happen INSIDE task bodies so the worker
  boots even when optional ML deps are missing.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from celery import chain

from backend.celery_app import PRIORITY_HIGH, PRIORITY_NORMAL, celery_app
from backend.celery_app.progress import set_job_progress

log = logging.getLogger("celery.tasks")

TERMINAL = {"completed", "failed"}


# ---------------------------------------------------------------- helpers
def _db():
    from backend.database import get_session_factory  # noqa: PLC0415
    return get_session_factory()()


def _log_error(db, *, job_id=None, user_id=None, source: str, message: str,
               detail: str | None = None) -> None:
    from backend.database import ErrorLog  # noqa: PLC0415
    try:
        db.add(ErrorLog(job_id=job_id, user_id=user_id, source=source,
                        message=message[:2000], detail=(detail or "")[:8000] or None))
        db.commit()
    except Exception as exc:
        log.warning("ErrorLog write failed: %s", exc)


def _notify_admins(subject: str, body: str) -> None:
    """Best-effort admin notification: email if configured, else log."""
    from backend.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    recipients = [e for e in settings.admin_email_set if e]
    if not recipients:
        log.warning("ADMIN NOTIFY (no admin emails configured): %s | %s", subject, body[:500])
        return
    try:
        from backend.agents.agent08_email import EmailAgent  # noqa: PLC0415
        agent = EmailAgent(settings)
        ok, _ = agent.is_configured()
        if not ok:
            log.warning("ADMIN NOTIFY (email unconfigured): %s | %s", subject, body[:500])
            return
        for rcpt in recipients:
            agent.send_recap_ready(to_email=rcpt, video_title="[admin] " + subject,
                                   summary=body, download_link="")
    except Exception as exc:
        log.warning("admin notify failed: %s", exc)


def _fail_job(db, job_id: str, stage: str, message: str, user_id: str | None = None) -> None:
    set_job_progress(db, job_id, stage=stage, status="failed", error=message,
                     message=f"Failed: {message[:200]}")
    _log_error(db, job_id=job_id, user_id=user_id, source=f"task:{stage}", message=message)
    _notify_admins(f"Job {job_id} failed at {stage}", message)


def _next(task_fn, job_id: str, priority: int) -> bool:
    """Enqueue the next pipeline stage honoring priority routing.

    Best-effort like enqueue_pipeline(): when the broker is unreachable
    the job stays in its current (non-failed) state instead of being
    marked failed for an infrastructure outage. Returns True if enqueued.
    """
    if not broker_reachable():
        log.warning("broker unreachable; job %s stays at current stage until a worker runs",
                    job_id)
        return False
    try:
        task_fn.apply_async(args=(job_id,), priority=min(9, max(0, priority or PRIORITY_NORMAL)))
        return True
    except Exception as exc:
        log.warning("celery enqueue failed (job %s stays at current stage): %s", job_id, exc)
        return False


def _backoff(task_self) -> int:
    return 60 * (2 ** min(task_self.request.retries, 4))


# ---------------------------------------------------------------- pipeline
@celery_app.task(bind=True, name="backend.celery_app.tasks.ingest_video",
                 max_retries=3, time_limit=600, soft_time_limit=540)
def ingest_video(self, video_id: str, job_id: str):
    """Re-validate the uploaded file, then hand off to processing."""
    from backend.database import Job, Video  # noqa: PLC0415

    db = _db()
    try:
        job = db.query(Job).filter_by(id=job_id).one_or_none()
        video = db.query(Video).filter_by(id=video_id).one_or_none()
        if job is None or video is None:
            log.error("ingest_video: video=%s job=%s not found", video_id, job_id)
            return
        set_job_progress(db, job_id, stage="ingesting", progress=5.0,
                         message="Validating upload…", status="processing")
        # Multi-container: with cloud storage the DB holds a storage KEY,
        # not a local path — materialize it locally first (no-op when the
        # file is already on this filesystem).
        from backend.storage import ensure_local  # noqa: PLC0415
        try:
            local_path = ensure_local(video.storage_path or "", video_id)
        except Exception as exc:
            _fail_job(db, job_id, "ingesting",
                      f"uploaded file missing: {video.storage_path} ({exc})",
                      user_id=job.user_id)
            return
        if not local_path.exists():
            _fail_job(db, job_id, "ingesting", f"uploaded file missing: {video.storage_path}",
                      user_id=job.user_id)
            return
        set_job_progress(db, job_id, stage="ingested", progress=10.0,
                         message="Upload validated")
        _next(process_video, job_id, job.priority)
        log.info("ingest_video done job=%s", job_id)
    except Exception as exc:
        log.exception("ingest_video job=%s crashed", job_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=_backoff(self))
        db2 = _db()
        try:
            _fail_job(db2, job_id, "ingesting", f"ingest crashed: {exc}")
        finally:
            db2.close()
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.celery_app.tasks.process_video",
                 max_retries=2, time_limit=1800, soft_time_limit=1650)
def process_video(self, job_id: str):
    """Agent02: normalize, extract audio/frames/scenes/thumbnails."""
    from backend.config import get_settings  # noqa: PLC0415
    from backend.database import Job, Video  # noqa: PLC0415

    db = _db()
    try:
        job = db.query(Job).filter_by(id=job_id).one_or_none()
        if job is None:
            log.error("process_video: job %s not found", job_id)
            return
        video = db.query(Video).filter_by(id=job.video_id).one_or_none()
        set_job_progress(db, job_id, stage="processing", progress=12.0,
                         message="Normalizing video…", status="processing")

        from backend.agents.agent02_processing import ProcessingAgent  # noqa: PLC0415
        settings = get_settings()
        agent = ProcessingAgent(Path(settings.STORAGE_ROOT) / "processing")
        # Resolve the input to a local file first: with cloud storage the
        # DB holds a storage KEY, not a path (ingest already materialized
        # it, so this is normally a cache hit).
        from backend.storage import ensure_local  # noqa: PLC0415
        input_path = ensure_local(video.storage_path or "", video.id)
        result = agent.process(str(input_path), job_id)
        if not result.ok:
            msg = "; ".join(result.errors) or "processing failed"
            if self.request.retries < self.max_retries:
                raise self.retry(exc=RuntimeError(msg), countdown=_backoff(self))
            _fail_job(db, job_id, "processing", msg, user_id=job.user_id)
            return

        job.result = {**(job.result or {}), "processing": {
            "normalized_path": result.normalized_path,
            "audio_path": result.audio_path,
            "frames_dir": result.frames_dir,
            "frame_count": len(result.frame_files),
            "frame_files": result.frame_files[:200],
            "thumbnails": result.thumbnails,
            "segments": result.segments,
            "duration_sec": result.duration_sec,
            "warnings": result.warnings,
        }}
        db.commit()
        set_job_progress(db, job_id, stage="processed", progress=30.0,
                         message="Video processed")
        _next(ai_analyze, job_id, job.priority)
        log.info("process_video done job=%s", job_id)
    except Exception as exc:
        # A Retry raised by the inner self.retry() above must propagate
        # untouched. Catching it here retried AGAIN (a second task
        # message for the same job) and then fell through to _fail_job,
        # marking the job failed on every retry. Live 2026-10-16: two
        # workers ran the same job seconds apart, both writing
        # normalized.mp4, and every normalize failed with 0 frames.
        from celery.exceptions import Retry  # noqa: PLC0415

        if isinstance(exc, Retry):
            raise
        log.exception("process_video job=%s crashed", job_id)
        if self.request.retries < self.max_retries and "crashed" not in str(exc)[:20]:
            try:
                raise self.retry(exc=exc, countdown=_backoff(self))
            except Exception:
                pass
        db2 = _db()
        try:
            _fail_job(db2, job_id, "processing", f"processing crashed: {exc}")
        finally:
            db2.close()
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.celery_app.tasks.ai_analyze",
                 max_retries=2, time_limit=2400, soft_time_limit=2250)
def ai_analyze(self, job_id: str):
    """Agents 03-06: speech -> vision -> summary -> highlights."""
    from backend.config import get_settings  # noqa: PLC0415
    from backend.database import Job, Video  # noqa: PLC0415

    db = _db()
    try:
        job = db.query(Job).filter_by(id=job_id).one_or_none()
        if job is None:
            log.error("ai_analyze: job %s not found", job_id)
            return
        settings = get_settings()
        prev = job.result or {}
        proc = prev.get("processing", {})
        lang = job.output_lang or "en"

        # Per-user transcription choice from video.meta (Settings BYOK):
        # provider "auto" = server chain; "gemini"/"groq" = that provider
        # only, with the user's own key when one was supplied (decrypted
        # transiently here, never logged).
        video = db.query(Video).filter_by(id=job.video_id).one_or_none()
        prefs = (video.meta or {}) if video is not None else {}
        speech_provider = prefs.get("transcription_provider", "auto")
        speech_key = None
        enc = prefs.get("transcription_key_enc")
        if enc:
            from backend.security.keyvault import decrypt_key  # noqa: PLC0415
            speech_key = decrypt_key(enc)

        from backend.ai_provider.manager import ProviderManager  # noqa: PLC0415
        manager = ProviderManager(settings)

        # -- agent03 speech --
        set_job_progress(db, job_id, stage="transcribing", progress=35.0,
                         message="Transcribing speech…", status="analyzing")
        from backend.agents.agent03_speech import SpeechAgent  # noqa: PLC0415
        speech = SpeechAgent(model_name=settings.WHISPER_MODEL,
                             device=settings.WHISPER_DEVICE,
                             provider_manager=manager)
        speech_out = speech.transcribe(proc.get("audio_path"), job_id,
                                       provider=speech_provider, key=speech_key)
        transcript = speech_out.get("transcript", [])

        # -- agent04 vision --
        set_job_progress(db, job_id, stage="vision", progress=50.0,
                         message="Analyzing visuals…")
        from backend.agents.agent04_vision import VisionAgent  # noqa: PLC0415
        vision_out = VisionAgent(provider_manager=manager).analyze(
            proc.get("frame_files", []), job_id)

        # -- agent05 summary --
        set_job_progress(db, job_id, stage="summarizing", progress=65.0,
                         message="Writing recap…")
        from backend.agents.agent05_summary import SummaryAgent  # noqa: PLC0415
        summary_out = SummaryAgent(manager).summarize(
            transcript, vision_out, job_id,
            duration_sec=proc.get("duration_sec"), lang=lang)

        # -- agent06 highlights --
        set_job_progress(db, job_id, stage="highlights", progress=78.0,
                         message="Picking highlights…")
        from backend.agents.agent06_highlights import HighlightsAgent  # noqa: PLC0415
        highlights_out = HighlightsAgent().select(
            transcript, proc.get("segments", []), vision_out, job_id,
            duration_sec=proc.get("duration_sec"))

        job.result = {**prev,
                      "speech": speech_out,
                      "vision": {"frames": vision_out.get("frames", [])[:50],
                                 "degraded": vision_out.get("degraded", True)},
                      "summary": summary_out,
                      "highlights": highlights_out.get("highlights", [])}
        db.commit()
        set_job_progress(db, job_id, stage="analyzed", progress=82.0,
                         message="Analysis complete")
        _next(render_recap, job_id, job.priority)
        log.info("ai_analyze done job=%s", job_id)
    except Exception as exc:
        log.exception("ai_analyze job=%s crashed", job_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=_backoff(self))
        db2 = _db()
        try:
            _fail_job(db2, job_id, "analyzing", f"AI analysis crashed: {exc}")
        finally:
            db2.close()
    finally:
        db.close()


def _translate_segments(settings, segments: list[dict], target_lang: str,
                        source_lang: str | None) -> list[dict]:
    """Translate subtitle segment texts to target_lang, keeping timestamps.

    Skips translation when the detected source language already matches
    the target. Returns the original segments on ANY failure (bad JSON,
    wrong count, provider error) — subtitles must never fail a render.
    """
    target = {"my": "Myanmar (Burmese)", "en": "English"}.get(target_lang)
    if target is None or not segments:
        return segments
    src = (source_lang or "").lower()
    if (target_lang == "my" and src in ("my", "mya", "myanmar", "burmese")) or \
       (target_lang == "en" and src in ("en", "eng", "english")):
        return segments
    try:
        import asyncio  # noqa: PLC0415
        import json  # noqa: PLC0415

        from backend.ai_provider.manager import ProviderManager  # noqa: PLC0415

        texts = [str(s.get("text", "")) for s in segments]
        prompt = (
            f"Translate each subtitle line to {target}. Return ONLY JSON: "
            '{"segments": [{"text": "..."}]} in the SAME order and SAME '
            "count as the input. Keep each line short and natural; do not "
            "add explanations.\nInput:\n"
            + json.dumps([{"text": t} for t in texts], ensure_ascii=False))
        out = asyncio.run(ProviderManager(settings).complete(
            "summary", prompt, json_mode=True, max_tokens=8000))
        text = out[0] if isinstance(out, tuple) else out
        # Gemini often wraps JSON in ```json fences — plain json.loads
        # would fail and silently fall back to the untranslated text.
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re  # noqa: PLC0415
            m = re.search(r"\{.*\}", text, re.S)
            if not m:
                raise
            data = json.loads(m.group(0))
        translated = data.get("segments", [])
        if not isinstance(translated, list) or len(translated) != len(segments):
            raise ValueError("translation segment count mismatch")
        result = []
        for seg, tr in zip(segments, translated, strict=True):
            result.append({**seg, "text": str(tr.get("text", seg.get("text", "")))})
        log.info("subtitles translated to %s: %d segments", target_lang, len(result))
        return result
    except Exception as exc:
        log.warning("subtitle translation to %s failed, keeping original: %s",
                    target_lang, exc)
        return segments


def _narration_text(summary: dict, transcript: list[dict]) -> str:
    """Narration text for TTS: the recap summary, with fallbacks.

    The summary step can fail (provider down / model retired) while the
    rest of the pipeline still runs. Previously an empty summary meant
    narration_text == "" and the TTS step silently never ran at all
    (live 2026-10-17: original audio kept, no TTS line in any log).
    Fall back to key points, then to the transcript itself, so TTS
    still narrates something in the recap language.
    """
    text = (summary.get("summary_short") or summary.get("description") or "").strip()
    if text:
        return text
    points = [str(p).strip() for p in (summary.get("key_points") or [])]
    points = [p for p in points if p]
    if points:
        return " ".join(points)
    spoken = " ".join(str(s.get("text", "")).strip() for s in (transcript or []))
    return spoken.strip()[:4000]


def _intro_outro_texts(prefs: dict, summary: dict) -> tuple[str | None, str | None]:
    """Resolve intro/outro card text: custom user text wins, else defaults
    (recap title / Thanks for watching). Disabled card -> None."""
    intro = None
    if prefs.get("intro_enabled", True):
        intro = (prefs.get("intro_text") or "").strip() or summary.get("title", "Video Recap")
    outro = None
    if prefs.get("outro_enabled", True):
        outro = (prefs.get("outro_text") or "").strip() or "Thanks for watching — AI Video Recap"
    return intro, outro


@celery_app.task(bind=True, name="backend.celery_app.tasks.render_recap",
                 max_retries=1, time_limit=3600, soft_time_limit=3300)
def render_recap(self, job_id: str):
    """Agent07: cut/concat highlights, subtitles, intro/outro, export MP4."""
    from backend.config import get_settings  # noqa: PLC0415
    from backend.database import Job, Output, Video  # noqa: PLC0415

    db = _db()
    try:
        job = db.query(Job).filter_by(id=job_id).one_or_none()
        if job is None:
            log.error("render_recap: job %s not found", job_id)
            return
        settings = get_settings()
        prev = job.result or {}
        proc = prev.get("processing", {})
        summary = prev.get("summary", {})
        transcript = (prev.get("speech", {}) or {}).get("transcript", [])
        highlights = prev.get("highlights", [])
        speech_lang = (prev.get("speech", {}) or {}).get("language")

        # Subtitle language (job.subtitle_language): the SRT must be IN
        # that language. Previously the raw transcript was written as-is,
        # so "Myanmar subtitles" came out in English. Translate the
        # segments (timestamps preserved) when needed; "none" means no
        # subtitles at all. Translation never fails the job — on any
        # error the original text is used.
        subtitle_lang = job.subtitle_language or "my"
        if subtitle_lang == "none":
            transcript = []
        elif transcript and subtitle_lang in ("my", "en"):
            transcript = _translate_segments(
                settings, transcript, subtitle_lang, speech_lang)

        set_job_progress(db, job_id, stage="rendering", progress=85.0,
                         message="Rendering recap video…", status="rendering")

        from backend.agents.agent07_rendering import RenderingAgent  # noqa: PLC0415
        renderer = RenderingAgent(Path(settings.STORAGE_ROOT) / "results")
        # Intro/outro toggles live in video.meta (see persist_ingestion);
        # missing keys mean "enabled" (backward compat for older jobs).
        video = db.query(Video).filter_by(id=job.video_id).one_or_none()
        prefs = (video.meta or {}) if video is not None else {}
        intro_enabled = prefs.get("intro_enabled", True)
        outro_enabled = prefs.get("outro_enabled", True)
        intro_text, outro_text = _intro_outro_texts(prefs, summary)
        voice_mode = prefs.get("voice_mode", "original")
        narration_text = ""
        tts_kwargs: dict = {}
        if voice_mode == "tts":
            # Narration = the recap summary in the recap language.
            # Falls back to key points / transcript when the summary
            # step failed, so TTS still runs (see _narration_text).
            narration_text = _narration_text(summary, transcript)
            log.info("render narration job=%s voice_mode=%s provider=%s voice=%s chars=%d",
                     job_id, voice_mode, tts_kwargs.get("tts_provider"),
                     tts_kwargs.get("tts_voice"), len(narration_text))
            tts_kwargs = {
                "tts_provider": prefs.get("tts_provider", "edge"),
                "tts_voice": prefs.get("tts_voice", "thiha"),
                "tts_rate": float(prefs.get("tts_rate", 1.0) or 1.0),
                "tts_pitch": int(prefs.get("tts_pitch", 0) or 0),
                "settings": settings,
            }
        result = renderer.render(
            proc.get("normalized_path"), highlights, transcript,
            summary.get("title", "Video Recap"), job_id,
            intro_text=intro_text,
            outro_text=outro_text,
            intro_enabled=bool(intro_enabled),
            outro_enabled=bool(outro_enabled),
            narration_text=narration_text or None,
            **tts_kwargs)

        if not result.ok:
            msg = "; ".join(result.errors) or "render failed"
            _fail_job(db, job_id, "rendering", msg, user_id=job.user_id)
            return

        # store outputs via the storage backend
        from backend.storage import get_storage  # noqa: PLC0415
        storage = get_storage()
        video_key = f"results/{job_id}/recap_final.mp4"
        storage.put(result.video_path, video_key)
        outputs = [Output(job_id=job_id, kind="recap_video",
                          storage_path=video_key,
                          size_bytes=Path(result.video_path).stat().st_size)]
        if result.subtitle_path and Path(result.subtitle_path).exists():
            srt_key = f"results/{job_id}/subtitles.srt"
            storage.put(result.subtitle_path, srt_key)
            outputs.append(Output(job_id=job_id, kind="subtitles",
                                  storage_path=srt_key,
                                  size_bytes=Path(result.subtitle_path).stat().st_size))
        for thumb in (proc.get("thumbnails") or [])[:1]:
            if Path(thumb).exists():
                tkey = f"thumbnails/{job_id}/thumb.jpg"
                storage.put(thumb, tkey)
                outputs.append(Output(job_id=job_id, kind="thumbnail",
                                      storage_path=tkey,
                                      size_bytes=Path(thumb).stat().st_size))
        db.add_all(outputs)
        job.result = {**prev, "render": {
            "video_key": video_key,
            "subtitle_mode": result.subtitle_mode,
            # Surface render warnings (e.g. TTS fallback / failure) in the
            # job result so the user isn't left guessing why the audio
            # is original instead of narration.
            "warnings": list(result.warnings or []),
            "warnings": result.warnings,
        }}
        db.commit()
        set_job_progress(db, job_id, stage="rendered", progress=95.0,
                         message="Recap video ready")
        _next(send_notification, job_id, job.priority)
        log.info("render_recap done job=%s", job_id)
    except Exception as exc:
        log.exception("render_recap job=%s crashed", job_id)
        db2 = _db()
        try:
            _fail_job(db2, job_id, "rendering", f"render crashed: {exc}")
        finally:
            db2.close()
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.celery_app.tasks.send_notification",
                 max_retries=3, time_limit=300, soft_time_limit=240)
def send_notification(self, job_id: str):
    """Agent08: email the user their recap is ready; then mark completed."""
    from backend.config import get_settings  # noqa: PLC0415
    from backend.database import Job, User  # noqa: PLC0415

    db = _db()
    try:
        job = db.query(Job).filter_by(id=job_id).one_or_none()
        if job is None:
            log.error("send_notification: job %s not found", job_id)
            return
        settings = get_settings()
        if job.status == "failed":
            # Never overwrite a recorded failure with "completed": a failed
            # stage (e.g. render) must stay failed even if notification runs.
            log.warning("send_notification job=%s already failed; leaving failed", job_id)
            return
        user = db.query(User).filter_by(id=job.user_id).one_or_none()
        summary = (job.result or {}).get("summary", {})

        download_link = f"{settings.API_BASE_URL}/api/results/{job_id}/download"
        try:
            from backend.agents.agent08_email import EmailAgent  # noqa: PLC0415
            EmailAgent(settings).send_recap_ready(
                to_email=(user.email if user else "") or "",
                video_title=summary.get("title", "your video"),
                summary=summary.get("summary_short", ""),
                download_link=download_link,
                recipient_name=(user.display_name if user else "") or "",
                user_id=job.user_id, job_id=job_id)
        except Exception as exc:
            # email must never fail the job; retry transiently then continue
            log.warning("send_notification job=%s email issue: %s", job_id, exc)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc, countdown=_backoff(self))

        set_job_progress(db, job_id, stage="done", progress=100.0,
                         message="Recap ready!", status="completed")
        log.info("send_notification done job=%s", job_id)
    except Exception as exc:
        log.exception("send_notification job=%s crashed", job_id)
        db2 = _db()
        try:
            _fail_job(db2, job_id, "notifying", f"notification crashed: {exc}")
        finally:
            db2.close()
    finally:
        db.close()


# ---------------------------------------------------------------- beat tasks
@celery_app.task(name="backend.celery_app.tasks.health_check_providers",
                 time_limit=300, soft_time_limit=240)
def health_check_providers():
    """Every 5 min: probe AI providers, persist to ProviderHealth."""
    import asyncio  # noqa: PLC0415

    from backend.ai_provider.manager import ProviderManager  # noqa: PLC0415
    from backend.config import get_settings  # noqa: PLC0415

    started = time.monotonic()
    try:
        manager = ProviderManager(get_settings())
        results = asyncio.run(manager.health_check_all())
        manager.persist_health(results)
        log.info("provider health: %s (%.1fs)",
                 {k: v["status"] for k, v in results.items()},
                 time.monotonic() - started)
        return {k: v["status"] for k, v in results.items()}
    except Exception as exc:
        log.exception("health_check_providers failed: %s", exc)
        return {"error": str(exc)[:300]}


@celery_app.task(name="backend.celery_app.tasks.cleanup_old_files",
                 time_limit=1800, soft_time_limit=1500)
def cleanup_old_files(max_age_days: int = 7):
    """Daily: delete temporary/processing artifacts older than N days."""
    from backend.config import get_settings  # noqa: PLC0415

    root = Path(get_settings().STORAGE_ROOT)
    cutoff = time.time() - max_age_days * 86400
    removed, freed = 0, 0
    for sub in ("temporary", "processing"):
        base = root / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    freed += path.stat().st_size
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    log.info("cleanup_old_files: removed %d files, freed %.1f MB", removed, freed / 1e6)
    return {"removed": removed, "freed_bytes": freed}


# Convenience: build the whole pipeline as a celery chain (used by API/tests).
def build_pipeline(video_id: str, job_id: str, priority: int = PRIORITY_NORMAL):
    return chain(
        ingest_video.s(video_id, job_id).set(priority=priority),
        process_video.s(job_id).set(priority=priority),
        ai_analyze.s(job_id).set(priority=priority),
        render_recap.s(job_id).set(priority=priority),
        send_notification.s(job_id).set(priority=priority),
    )


def broker_reachable(timeout: float = 1.5) -> bool:
    """Quick check: is the Celery broker actually up?

    Must parse the FULL broker URL (via from_url) — building a client
    from host/port alone drops the password (and db index), so a
    password-protected broker (Railway Redis) answers NOAUTH and the
    check wrongly reports unreachable. Live incident 2026-10-16: the
    API's /ready Redis check (from_url) said ok while enqueue skipped
    every job as "broker unreachable", so uploads returned 201 but no
    worker task ever started.
    """
    try:
        import redis  # noqa: PLC0415

        from backend.config import get_settings  # noqa: PLC0415
        client = redis.Redis.from_url(
            get_settings().CELERY_BROKER_URL,
            socket_connect_timeout=timeout, socket_timeout=timeout)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


def enqueue_pipeline(video_id: str, job_id: str,
                     priority: int = PRIORITY_NORMAL) -> bool:
    """
    Dispatch ingest_video to the upload queue. Returns False (job stays
    "queued") when the broker is unreachable — never raises, never hangs on
    kombu connection retries.
    """
    if not broker_reachable():
        log.warning("broker unreachable; job %s stays queued until a worker runs",
                    job_id)
        return False
    try:
        ingest_video.apply_async(args=(video_id, job_id),
                                 queue="video_upload_queue",
                                 priority=min(9, max(0, priority)))
        return True
    except Exception as exc:
        log.warning("celery enqueue failed (job %s stays queued): %s", job_id, exc)
        return False


__all__ = [
    "ingest_video",
    "process_video",
    "ai_analyze",
    "render_recap",
    "send_notification",
    "health_check_providers",
    "cleanup_old_files",
    "build_pipeline",
    "broker_reachable",
    "enqueue_pipeline",
    "TERMINAL",
]
