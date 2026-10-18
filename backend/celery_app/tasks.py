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


def _next(task_fn, job_id: str, priority: int,
         user_keys: dict[str, list[str]] | None = None) -> bool:
    """Enqueue the next pipeline stage honoring priority routing.

    Best-effort like enqueue_pipeline(): when the broker is unreachable
    the job stays in its current (non-failed) state instead of being
    marked failed for an infrastructure outage. Returns True if enqueued.

    user_keys (per-user AI keys) travel as task kwargs — in-memory
    through the broker only, never written to the database. Only the
    stages that call AI providers receive them.
    """
    if not broker_reachable():
        log.warning("broker unreachable; job %s stays at current stage until a worker runs",
                    job_id)
        return False
    try:
        kwargs = {"user_keys": user_keys} if user_keys else {}
        task_fn.apply_async(args=(job_id,), kwargs=kwargs,
                            priority=min(9, max(0, priority or PRIORITY_NORMAL)))
        return True
    except Exception as exc:
        log.warning("celery enqueue failed (job %s stays at current stage): %s", job_id, exc)
        return False


def _backoff(task_self) -> int:
    return 60 * (2 ** min(task_self.request.retries, 4))


# ---------------------------------------------------------------- pipeline
@celery_app.task(bind=True, name="backend.celery_app.tasks.ingest_video",
                 max_retries=3, time_limit=600, soft_time_limit=540)
def ingest_video(self, video_id: str, job_id: str,
                 user_keys: dict[str, list[str]] | None = None):
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
        _next(process_video, job_id, job.priority, user_keys=user_keys)
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
def process_video(self, job_id: str,
                  user_keys: dict[str, list[str]] | None = None):
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
        _next(ai_analyze, job_id, job.priority, user_keys=user_keys)
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


def _recap_style_config(prefs: dict) -> dict:
    """Map the user's recap style (video.meta) to pipeline params.

    Returns {"name", "top_n", "tone"}. There are deliberately NO
    minute caps (user 2026-10-18): the recap is as long/short as the
    AI script, and the render step stretches the video to the
    narration. top_n is the highlight candidate pool; tone guides
    the summary prompt.
    """
    name = prefs.get("recap_style", "detailed")
    if name not in ("short", "detailed", "cinematic", "custom"):
        name = "detailed"
    top_n = {"short": 4, "cinematic": 8}.get(name, 12)
    tone = (prefs.get("recap_tone") or "")[:200] if name == "custom" else ""
    return {"name": name, "top_n": top_n, "tone": tone}


@celery_app.task(bind=True, name="backend.celery_app.tasks.ai_analyze",
                 max_retries=2, time_limit=2400, soft_time_limit=2250)
def ai_analyze(self, job_id: str,
               user_keys: dict[str, list[str]] | None = None):
    """Agents 03-06: speech -> vision -> summary -> highlights.

    user_keys: per-user AI keys for this job only ({"gemini": [key],
    "groq": [key]}). They arrive as task kwargs from the upload, live
    in memory for this job, and are never written to the database —
    the user's browser is the only place they are saved. A provided
    list REPLACES the owner keys for that provider, so the job spends
    the user's own quota, never the owner's. No user keys -> owner
    (env) keys, as before.
    """
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
        video = db.query(Video).filter_by(id=job.video_id).one_or_none()
        prefs = (video.meta or {}) if video is not None else {}
        style = _recap_style_config(prefs)
        log.info("ai_analyze job=%s recap_style=%s top_n=%d",
                 job_id, style["name"], style["top_n"])

        # Per-user AI keys arrive as task kwargs (see docstring):
        # no key material is read from video.meta anymore.
        user_keys = user_keys or {}

        from backend.ai_provider.manager import ProviderManager  # noqa: PLC0415
        manager = ProviderManager(settings, user_keys=user_keys)

        # -- agent03 speech --
        set_job_progress(db, job_id, stage="transcribing", progress=35.0,
                         message="Transcribing speech…", status="analyzing")
        from backend.agents.agent03_speech import SpeechAgent  # noqa: PLC0415
        speech = SpeechAgent(model_name=settings.WHISPER_MODEL,
                             device=settings.WHISPER_DEVICE,
                             provider_manager=manager)
        # One chain for every job (groq -> gemini -> huggingface): the
        # manager spends the user's own key for any provider they
        # supplied one for, else the owner key. No per-job provider
        # choice anymore — the user enters keys once, in Settings.
        speech_out = speech.transcribe(proc.get("audio_path"), job_id)
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
            duration_sec=proc.get("duration_sec"), lang=lang, style=style)

        # -- agent06 highlights --
        set_job_progress(db, job_id, stage="highlights", progress=78.0,
                         message="Picking highlights…")
        from backend.agents.agent06_highlights import HighlightsAgent  # noqa: PLC0415
        highlights_out = HighlightsAgent(
            top_n=style["top_n"]).select(
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
        _next(render_recap, job_id, job.priority, user_keys=user_keys)
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


def _complete_with_retry(settings, prompt: str, *, json_mode: bool,
                        max_tokens: int, attempts: int = 2,
                        sleep_sec: float = 20.0,
                        user_keys: dict[str, list[str]] | None = None) -> str:
    """One provider text call with retries.

    Each attempt waits out the shared Gemini quota cooldown first
    (inside the provider); between attempts we sleep so a per-minute
    quota window can reset. Raises the last error when all attempts
    fail. Only used for translation, where a wait is cheaper than
    shipping the wrong language."""
    import asyncio  # noqa: PLC0415
    import time  # noqa: PLC0415

    from backend.ai_provider.manager import ProviderManager  # noqa: PLC0415

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            out = asyncio.run(ProviderManager(
                settings, user_keys=user_keys).complete(
                "summary", prompt, json_mode=json_mode, max_tokens=max_tokens))
            return out[0] if isinstance(out, tuple) else out
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts:
                log.warning("translation attempt %d/%d failed, retrying in %.0fs: %s",
                            attempt, attempts, sleep_sec, exc)
                time.sleep(sleep_sec)
    assert last_exc is not None
    raise last_exc


def _contains_myanmar(text: str) -> bool:
    return any("\u1000" <= ch <= "\u109f" for ch in (text or ""))


def _is_quota_error_text(text: str) -> bool:
    """True when an error string signals provider quota exhaustion:
    HTTP 429, the word 'quota', or 'keys exhausted'. Used to flag jobs
    whose AI output is incomplete because quota ran out, so the result
    page can warn instead of silently showing empty output."""
    t = (text or "").lower()
    return "429" in t or "quota" in t or "exhausted" in t


def _job_hit_quota(prev: dict) -> bool:
    """True when any stored AI-stage error signals quota exhaustion
    (speech / summary / vision frame errors). Translation failures in
    render are not separately tracked — they use the same provider
    pool, so a quota wall there almost always shows up in these
    earlier stages first."""
    speech_err = (prev.get("speech", {}) or {}).get("error", "")
    summary_err = (prev.get("summary", {}) or {}).get("error", "")
    vision = prev.get("vision", {}) or {}
    errs = [speech_err, summary_err, vision.get("error", "")]
    errs += [f.get("error", "") for f in vision.get("frames", [])
             if isinstance(f, dict)]
    return any(_is_quota_error_text(e) for e in errs)


def _translate_segments(settings, segments: list[dict], target_lang: str,
                        source_lang: str | None,
                        user_keys: dict[str, list[str]] | None = None) -> tuple[list[dict], bool]:
    """Translate subtitle segment texts to target_lang, keeping timestamps.

    Skips translation when the detected source language already matches
    the target. Returns (segments, ok): ok is False when translation
    was needed but every attempt failed — the caller surfaces that as
    a visible warning instead of silently shipping the wrong language.
    Translation must never fail a render.
    """
    target = {"my": "Myanmar (Burmese)", "en": "English"}.get(target_lang)
    if target is None or not segments:
        return segments, True
    src = (source_lang or "").lower()
    if (target_lang == "my" and src in ("my", "mya", "myanmar", "burmese")) or \
       (target_lang == "en" and src in ("en", "eng", "english")):
        return segments, True
    try:
        import json  # noqa: PLC0415

        texts = [str(s.get("text", "")) for s in segments]
        prompt = (
            f"Translate each subtitle line to {target}. Return ONLY JSON: "
            '{"segments": [{"text": "..."}]} in the SAME order and SAME '
            "count as the input. Keep each line short and natural; do not "
            "add explanations.\nInput:\n"
            + json.dumps([{"text": t} for t in texts], ensure_ascii=False))
        text = _complete_with_retry(settings, prompt, json_mode=True, max_tokens=8000,
                                  user_keys=user_keys)
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
        return result, True
    except Exception as exc:
        log.warning("subtitle translation to %s failed, keeping original: %s",
                    target_lang, exc)
        return segments, False


def _translate_text(settings, text: str, target_lang: str,
                    source_lang: str | None,
                    user_keys: dict[str, list[str]] | None = None) -> tuple[str, bool]:
    """Translate one free-text passage (TTS narration) to target_lang.

    Returns (text, ok). Skips when the text already looks like the
    target language. On failure returns the original text with
    ok=False so the caller can warn instead of silently speaking
    the wrong language."""
    target = {"my": "Myanmar (Burmese)", "en": "English"}.get(target_lang)
    if target is None or not (text or "").strip():
        return text, True
    if target_lang == "my" and _contains_myanmar(text):
        log.info("narration already in %s, skipping translation", target_lang)
        return text, True
    if target_lang == "en" and text.isascii():
        log.info("narration already in %s, skipping translation", target_lang)
        return text, True
    src = (source_lang or "").lower()
    if (target_lang == "my" and src in ("my", "mya", "myanmar", "burmese")) or \
       (target_lang == "en" and src in ("en", "eng", "english")):
        return text, True
    try:
        prompt = (
            f"Translate the following text to {target}. Return ONLY the "
            f"translated text, no explanations, no quotes.\n\n{text}")
        out = _complete_with_retry(settings, prompt, json_mode=False, max_tokens=4000,
                                   user_keys=user_keys)
        translated = (out or "").strip()
        if not translated:
            raise ValueError("empty translation")
        log.info("narration translated to %s: %d chars", target_lang, len(translated))
        return translated, True
    except Exception as exc:
        log.warning("narration translation to %s failed, keeping original: %s",
                    target_lang, exc)
        return text, False


def _narration_text(summary: dict, transcript: list[dict]) -> str:
    """Narration text for TTS: the DETAILED recap summary, with fallbacks.

    The user chose (2026-10-18) narration from the detailed summary so
    recaps are longer: the video follows the narration length, and the
    narration follows the full story, not just the 2-3 sentence short
    version.

    The summary step can fail (provider down / model retired) while the
    rest of the pipeline still runs. Previously an empty summary meant
    narration_text == "" and the TTS step silently never ran at all
    (live 2026-10-17: original audio kept, no TTS line in any log).
    Fall back to the short summary, then key points, then the transcript
    itself, so TTS still narrates something in the recap language.
    """
    text = (summary.get("summary_long") or summary.get("summary_short")
            or summary.get("description") or "").strip()
    if text:
        return text
    points = [str(p).strip() for p in (summary.get("key_points") or [])]
    points = [p for p in points if p]
    if points:
        return " ".join(points)
    spoken = " ".join(str(s.get("text", "")).strip() for s in (transcript or []))
    return spoken.strip()[:4000]


def _intro_outro_texts(prefs: dict, summary: dict) -> tuple[str | None, str | None]:
    """Resolve fallback text-card text (used when no intro/outro VIDEO
    was uploaded): recap title for intro, Thanks for watching for
    outro. Disabled card -> None. There is no custom-text input any
    more — intro/outro are uploaded videos, not typed text."""
    intro = None
    if prefs.get("intro_enabled", True):
        intro = summary.get("title", "Video Recap")
    outro = None
    if prefs.get("outro_enabled", True):
        outro = "Thanks for watching — AI Video Recap"
    return intro, outro


def _download_side_video(job_id: str, storage_key: str, slot: str,
                         settings) -> str | None:
    """Download an uploaded intro/outro video (storage key) to a local
    file for FFmpeg. Returns the local path or None when the side video
    is missing/unreadable — the renderer then falls back to the text
    card, never failing the job over a decorative part."""
    from pathlib import Path  # noqa: PLC0415

    from backend.storage import get_storage  # noqa: PLC0415

    try:
        dest = Path(settings.STORAGE_ROOT) / "results" / job_id / f"{slot}_src.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        get_storage().download(storage_key, dest)
        return str(dest) if dest.exists() else None
    except Exception as exc:
        log.warning("render %s video download failed job=%s: %s", slot, job_id, exc)
        return None


@celery_app.task(bind=True, name="backend.celery_app.tasks.render_recap",
                 max_retries=1, time_limit=3600, soft_time_limit=3300)
def render_recap(self, job_id: str,
                 user_keys: dict[str, list[str]] | None = None):
    """Agent07: cut/concat highlights, subtitles, intro/outro, export MP4.

    user_keys: per-user AI keys for this job only (task kwargs, never
    written to the database). Translations in this step spend the
    user's own quota when they supplied keys.
    """
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

        # Per-user AI keys arrive as task kwargs (see ai_analyze).
        user_keys = user_keys or {}

        # Subtitle language (job.subtitle_language): the SRT must be IN
        # that language. Previously the raw transcript was written as-is,
        # so "Myanmar subtitles" came out in English. Translate the
        # segments (timestamps preserved) when needed; "none" means no
        # subtitles at all. Translation never fails the job — on any
        # failure the original text is used AND a warning is surfaced
        # on the result page (no silent wrong-language subtitles).
        subtitle_lang = job.subtitle_language or "my"
        subtitles_failed = False
        if subtitle_lang == "none":
            transcript = []
        elif transcript and subtitle_lang in ("my", "en"):
            transcript, subtitles_ok = _translate_segments(
                settings, transcript, subtitle_lang, speech_lang,
                user_keys=user_keys)
            subtitles_failed = not subtitles_ok

        from backend.agents.agent07_rendering import RenderingAgent  # noqa: PLC0415
        renderer = RenderingAgent(Path(settings.STORAGE_ROOT) / "results")
        # Intro/outro toggles live in video.meta (see persist_ingestion);
        # missing keys mean "enabled" (backward compat for older jobs).
        video = db.query(Video).filter_by(id=job.video_id).one_or_none()
        prefs = (video.meta or {}) if video is not None else {}
        # Output mode: "recap" (default) builds a condensed recap from
        # highlight clips; "dubbing" keeps the FULL original video and
        # replaces its audio with TTS narration of the full translated
        # transcript. Dubbing ignores intro/outro (the output IS the
        # original video, dubbed).
        output_mode = prefs.get("output_mode", "recap")
        if output_mode not in ("recap", "dubbing"):
            output_mode = "recap"
        set_job_progress(db, job_id, stage="rendering", progress=85.0,
                         message=("Rendering dubbed video…" if output_mode == "dubbing"
                                  else "Rendering recap video…"), status="rendering")
        intro_enabled = prefs.get("intro_enabled", True) and output_mode != "dubbing"
        outro_enabled = prefs.get("outro_enabled", True) and output_mode != "dubbing"
        intro_text, outro_text = _intro_outro_texts(prefs, summary)
        # Uploaded intro/outro VIDEOS (storage keys in video.meta) win
        # over the text cards. Materialize them locally for FFmpeg; a
        # missing/unreadable side video falls back to the text card in
        # the renderer (never fails the job).
        intro_clip = outro_clip = None
        if intro_enabled and prefs.get("intro_video_key"):
            intro_clip = _download_side_video(
                job_id, prefs["intro_video_key"], "intro", settings)
        if outro_enabled and prefs.get("outro_video_key"):
            outro_clip = _download_side_video(
                job_id, prefs["outro_video_key"], "outro", settings)
        voice_mode = prefs.get("voice_mode", "original")
        narration_text = ""
        narration_failed = False
        tts_kwargs: dict = {}
        if voice_mode == "tts":
            # DUBBING: narration = the FULL translated transcript (the
            # dialogue itself, dubbed), not the recap summary. Falls
            # back to the summary narration when there is no transcript
            # (e.g. no speech detected), so TTS still runs.
            if output_mode == "dubbing" and transcript:
                narration_text = " ".join(
                    (seg.get("text") or "").strip()
                    for seg in transcript).strip()
                output_lang = job.output_lang or "my"
                narration_ok = True
                # The transcript is ALREADY translated above, so the
                # text is in the target language; _translate_text
                # would skip it. Only re-translate when it does not
                # look like the target language (kept original text).
                if narration_text and output_lang in ("my", "en"):
                    narration_text, narration_ok = _translate_text(
                        settings, narration_text, output_lang, speech_lang,
                        user_keys=user_keys)
                narration_failed = not narration_ok
            else:
                # RECAP: narration = the recap summary in the recap
                # language. Falls back to key points / transcript when
                # the summary step failed, so TTS still runs (see
                # _narration_text). The fallback is usually ENGLISH
                # (the transcript language) while the user asked for
                # Myanmar speech — Thiha reading English text is NOT a
                # Myanmar voiceover. Translate the narration to the
                # job's output language first; if that fails, warn
                # visibly instead of silently speaking English.
                narration_text = _narration_text(summary, transcript)
                output_lang = job.output_lang or "my"
                if narration_text.strip() and output_lang in ("my", "en"):
                    narration_text, narration_ok = _translate_text(
                        settings, narration_text, output_lang, speech_lang,
                        user_keys=user_keys)
                    narration_failed = not narration_ok
            tts_kwargs = {
                "tts_provider": prefs.get("tts_provider", "edge"),
                "tts_voice": prefs.get("tts_voice", "thiha"),
                "tts_rate": float(prefs.get("tts_rate", 1.0) or 1.0),
                "tts_pitch": int(prefs.get("tts_pitch", 0) or 0),
                "settings": settings,
            }
            log.info("render narration job=%s voice_mode=%s provider=%s voice=%s chars=%d",
                     job_id, voice_mode, tts_kwargs.get("tts_provider"),
                     tts_kwargs.get("tts_voice"), len(narration_text))
        result = renderer.render(
            proc.get("normalized_path"), highlights, transcript,
            summary.get("title", "Video Recap"), job_id,
            output_mode=output_mode,
            intro_text=intro_text,
            outro_text=outro_text,
            intro_enabled=bool(intro_enabled),
            outro_enabled=bool(outro_enabled),
            intro_clip=intro_clip,
            outro_clip=outro_clip,
            narration_text=narration_text or None,
            **tts_kwargs)

        if not result.ok:
            msg = "; ".join(result.errors) or "render failed"
            _fail_job(db, job_id, "rendering", msg, user_id=job.user_id)
            return

        # Surface translation failures as result-page warnings: a
        # wrong-language subtitle track or narration must never be
        # presented as if it were the language the user selected.
        if subtitles_failed:
            sub_name = {"my": "Myanmar", "en": "English"}.get(subtitle_lang, subtitle_lang)
            result.warnings.append(
                f"subtitles not translated to {sub_name}; showing original language")
        if narration_failed:
            narr_name = {"my": "Myanmar", "en": "English"}.get(
                job.output_lang or "my", job.output_lang or "my")
            result.warnings.append(
                f"narration not translated to {narr_name}; speaking original text")

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
        job.result = {**prev,
                      # Quota-exhaustion flag: the result page shows a
                      # quota warning banner (when the user enabled
                      # that option) instead of silently empty output.
                      "quota_exhausted": _job_hit_quota(prev),
                      "render": {
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
def build_pipeline(video_id: str, job_id: str, priority: int = PRIORITY_NORMAL,
                   user_keys: dict[str, list[str]] | None = None):
    keys_kw = {"user_keys": user_keys} if user_keys else {}
    return chain(
        ingest_video.s(video_id, job_id, **keys_kw).set(priority=priority),
        process_video.s(job_id, **keys_kw).set(priority=priority),
        ai_analyze.s(job_id, **keys_kw).set(priority=priority),
        render_recap.s(job_id, **keys_kw).set(priority=priority),
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
                     priority: int = PRIORITY_NORMAL,
                     user_keys: dict[str, list[str]] | None = None) -> bool:
    """
    Dispatch ingest_video to the upload queue. Returns False (job stays
    "queued") when the broker is unreachable — never raises, never hangs on
    kombu connection retries.

    user_keys travel as task kwargs (in-memory through the broker only,
    never written to the database) and are forwarded stage to stage.
    """
    if not broker_reachable():
        log.warning("broker unreachable; job %s stays queued until a worker runs",
                    job_id)
        return False
    try:
        kwargs = {"user_keys": user_keys} if user_keys else {}
        ingest_video.apply_async(args=(video_id, job_id), kwargs=kwargs,
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
