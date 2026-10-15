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


def reset_storage_cache() -> None:
    get_storage.cache_clear()


__all__ = ["build_storage", "get_storage", "reset_storage_cache"]
