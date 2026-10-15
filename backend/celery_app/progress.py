"""
Job progress reporting: writes to the Job row AND publishes to Redis pub/sub.

The SSE endpoint (/api/jobs/{id}/stream) consumes progress via Redis when
available and falls back to polling the Job row — so progress always works
even when Redis is down.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("celery.progress")

_CHANNEL = "job:{job_id}:progress"


def _redis_client():
    try:
        import redis  # noqa: PLC0415 - optional at runtime
        from backend.config import get_settings  # noqa: PLC0415
        return redis.from_url(get_settings().REDIS_URL, socket_timeout=2)
    except Exception as exc:
        log.debug("redis unavailable: %s", exc)
        return None


def set_job_progress(db, job_id: str, *, stage: str | None = None,
                     progress: float | None = None,
                     message: str | None = None,
                     status: str | None = None,
                     error: str | None = None) -> None:
    """Update the Job row and publish the event to Redis (best effort)."""
    from backend.database import Job  # noqa: PLC0415

    job = db.query(Job).filter_by(id=job_id).one_or_none()
    payload: dict[str, Any] = {"job_id": job_id}
    if job is not None:
        if stage is not None:
            job.stage = stage
            payload["stage"] = stage
        if progress is not None:
            job.progress = max(0.0, min(100.0, float(progress)))
            payload["progress"] = job.progress
        if message is not None:
            payload["message"] = message
        if status is not None:
            job.status = status
            payload["status"] = status
        if error is not None:
            job.error = error
            payload["error"] = error
        db.commit()
    else:
        if stage is not None:
            payload["stage"] = stage
        if progress is not None:
            payload["progress"] = progress
        if message is not None:
            payload["message"] = message
        if status is not None:
            payload["status"] = status
        log.warning("set_job_progress: job %s not found", job_id)

    publish_progress(job_id, payload)


def publish_progress(job_id: str, payload: dict[str, Any]) -> None:
    """Publish a progress event to Redis pub/sub. Never raises."""
    client = _redis_client()
    if client is None:
        return
    try:
        client.publish(_CHANNEL.format(job_id=job_id), json.dumps(payload))
    except Exception as exc:
        log.debug("redis publish failed: %s", exc)
    finally:
        try:
            client.close()
        except Exception:
            pass


def subscribe_progress(job_id: str, timeout: float = 300.0):
    """
    Generator yielding progress dicts from Redis pub/sub for up to `timeout`
    seconds. Yields nothing (and returns) when Redis is unavailable.
    """
    client = _redis_client()
    if client is None:
        return
    try:
        pubsub = client.pubsub()
        pubsub.subscribe(_CHANNEL.format(job_id=job_id))
        deadline = __import__("time").monotonic() + timeout
        while __import__("time").monotonic() < deadline:
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                try:
                    yield json.loads(msg["data"])
                except (ValueError, TypeError):
                    continue
    except Exception as exc:
        log.debug("redis subscribe failed: %s", exc)
    finally:
        try:
            pubsub.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass


def channel_name(job_id: str) -> str:
    return _CHANNEL.format(job_id=job_id)


def open_subscriber(job_id: str):
    """
    Open a non-blocking Redis pub/sub subscriber for a job, or return None
    when Redis is unavailable. Use drain_subscriber() to pull pending events.
    """
    client = _redis_client()
    if client is None:
        return None
    try:
        pubsub = client.pubsub()
        pubsub.subscribe(_CHANNEL.format(job_id=job_id))
        # stash the client so callers can close both
        pubsub._recap_client = client  # type: ignore[attr-defined]
        return pubsub
    except Exception as exc:
        log.debug("redis subscribe failed: %s", exc)
        try:
            client.close()
        except Exception:
            pass
        return None


def drain_subscriber(pubsub) -> list[dict]:
    """Pull all pending events without blocking."""
    events: list[dict] = []
    try:
        while True:
            msg = pubsub.get_message(timeout=0)
            if msg is None:
                break
            if msg.get("type") == "message":
                try:
                    events.append(json.loads(msg["data"]))
                except (ValueError, TypeError):
                    continue
    except Exception as exc:
        log.debug("redis drain failed: %s", exc)
    return events


def close_subscriber(pubsub) -> None:
    try:
        pubsub.close()
    except Exception:
        pass
    try:
        pubsub._recap_client.close()  # type: ignore[attr-defined]
    except Exception:
        pass
