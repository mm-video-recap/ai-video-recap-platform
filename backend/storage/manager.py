"""
Storage manager: picks the backend from STORAGE_PROVIDER.

local (default) always works. r2 / supabase degrade gracefully to local with
a warning when credentials or optional dependencies are missing — the app
never crashes because a cloud bucket is unconfigured.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from backend.config import Settings, get_settings
from backend.storage.base import StorageBackend
from backend.storage.local import LocalStorage

log = logging.getLogger("storage")


def build_storage(settings: Settings | None = None) -> StorageBackend:
    settings = settings or get_settings()
    provider = (settings.STORAGE_PROVIDER or "local").lower()

    if provider == "r2":
        try:
            from backend.storage.r2 import R2Storage  # noqa: PLC0415

            return R2Storage(
                account_id=settings.R2_ACCOUNT_ID,
                access_key=settings.R2_ACCESS_KEY_ID,
                secret_key=settings.R2_SECRET_ACCESS_KEY,
                bucket_uploads=settings.R2_BUCKET_UPLOADS,
                bucket_results=settings.R2_BUCKET_RESULTS,
                bucket_temp=settings.R2_BUCKET_TEMP,
            )
        except Exception as exc:
            log.warning("R2 storage unavailable (%s); falling back to local", exc)

    elif provider == "supabase":
        try:
            from backend.storage.supabase_store import SupabaseStorage  # noqa: PLC0415

            return SupabaseStorage(
                supabase_url=settings.SUPABASE_URL,
                service_key=settings.SUPABASE_KEY,
                bucket=settings.SUPABASE_STORAGE_BUCKET,
            )
        except Exception as exc:
            log.warning("Supabase storage unavailable (%s); falling back to local", exc)

    elif provider != "local":
        log.warning("unknown STORAGE_PROVIDER=%r; using local", provider)

    return LocalStorage(settings.STORAGE_ROOT)


@lru_cache
def get_storage() -> StorageBackend:
    return build_storage()


def ensure_local(storage_path: str, video_id: str) -> Path:
    """Return a local filesystem Path for a stored upload.

    - Local provider: `storage_path` is already an absolute local path —
      returned as-is.
    - Cloud providers (supabase/r2): `storage_path` is a storage KEY —
      download it once to the local cache
      ``<STORAGE_ROOT>/uploads/<video_id>/original<ext>`` and return that
      path. Reuses the cached copy when it already exists.

    This is what makes multi-container deploys work: the API uploads to
    shared storage, and the worker materializes the file locally before
    FFmpeg reads it. Live incident 2026-10-16: with local storage the
    worker looked for /app/storage/... on ITS OWN filesystem and every
    job failed at ingest with "uploaded file missing".
    """
    from pathlib import Path as _Path  # noqa: PLC0415 - local import, manager is hot

    candidate = _Path(storage_path or "")
    if candidate.is_absolute() and candidate.exists():
        return candidate
    settings = get_settings()
    key = (storage_path or "").lstrip("/")
    ext = _Path(key).suffix or ".mp4"
    target = _Path(settings.STORAGE_ROOT) / "uploads" / video_id / f"original{ext}"
    if target.exists() and target.stat().st_size > 0:
        return target
    return get_storage().download(key, target)


def reset_storage_cache() -> None:
    get_storage.cache_clear()


__all__ = ["build_storage", "get_storage", "reset_storage_cache"]
