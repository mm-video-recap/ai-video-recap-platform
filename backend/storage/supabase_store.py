"""
Supabase Storage backend (plain httpx against the Storage REST API).

No supabase-py dependency required. Keys live in env only.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from backend.storage.base import StorageBackend

log = logging.getLogger("storage.supabase")


class SupabaseStorage(StorageBackend):
    name = "supabase"

    def __init__(self, supabase_url: str, service_key: str, bucket: str):
        if not (supabase_url and service_key and bucket):
            raise RuntimeError("Supabase storage not configured")
        self._base = supabase_url.rstrip("/")
        self._bucket = bucket
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }

    def _obj_url(self, key: str) -> str:
        return f"{self._base}/storage/v1/object/{self._bucket}/{key.lstrip('/')}"

    def put(self, local_path: str | Path, key: str) -> str:
        data = Path(local_path).read_bytes()
        resp = httpx.post(
            self._obj_url(key),
            headers={**self._headers, "Content-Type": "application/octet-stream"},
            content=data,
            timeout=120,
        )
        resp.raise_for_status()
        return key

    def get_url(self, key: str, expires_sec: int = 3600) -> str:
        resp = httpx.post(
            f"{self._base}/storage/v1/object/sign/{self._bucket}/{key.lstrip('/')}",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"expiresIn": expires_sec},
            timeout=30,
        )
        resp.raise_for_status()
        signed = resp.json().get("signedURL", "")
        return f"{self._base}{signed}" if signed.startswith("/") else signed

    def delete(self, key: str) -> None:
        try:
            httpx.delete(
                f"{self._base}/storage/v1/object/{self._bucket}",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"prefixes": [key.lstrip("/")]},
                timeout=30,
            ).raise_for_status()
        except Exception as exc:  # best effort
            log.warning("supabase delete failed for %s: %s", key, exc)

    def exists(self, key: str) -> bool:
        try:
            resp = httpx.head(self._obj_url(key), headers=self._headers, timeout=15)
            return resp.status_code == 200
        except Exception:
            return False
