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
            # x-upsert: overwrite when the key already exists (Supabase
            # POST otherwise 400s with "Duplicate"). Live 2026-10-16:
            # upload puts 400d and the bare raise_for_status hid the
            # Supabase error body, so log it — it names the real cause.
            headers={**self._headers,
                      "Content-Type": "application/octet-stream",
                      "x-upsert": "true"},
            content=data,
            timeout=120,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            log.warning("supabase put failed for %s: %s %s",
                        key, resp.status_code, resp.text[:500])
            if "row-level security" in resp.text:
                # service_role bypasses RLS; the anon key does not. This
                # exact failure (2026-10-16) meant SUPABASE_KEY on Railway
                # held the anon key instead of the service_role key.
                log.warning(
                    "supabase put hit an RLS policy: SUPABASE_KEY is "
                    "probably the anon key, not the service_role key")
            raise
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
        # storage-api returns signedURL relative to the STORAGE API root
        # ("/object/sign/...", WITHOUT "/storage/v1"). supabase-js
        # prepends its storage root (".../storage/v1") itself. We must
        # do the same: prepending only the bare project URL produced
        # "https://<ref>.supabase.co/object/sign/..." which the gateway
        # rejects with {"error":"requested path is invalid"} — live
        # 2026-10-16: video player + both downloads failed that way
        # while sign itself returned 200 and the object existed.
        if signed.startswith("/storage/v1/"):
            return f"{self._base}{signed}"
        if signed.startswith("http://") or signed.startswith("https://"):
            return signed
        if signed.startswith("/"):
            return f"{self._base}/storage/v1{signed}"
        return f"{self._base}/storage/v1/{signed.lstrip('/')}" if signed else signed

    def delete(self, key: str) -> None:
        try:
            # httpx.delete() takes no body kwargs — json= raises
            # TypeError ("delete() got an unexpected keyword argument
            # 'json'"). Live 2026-10-16: every cleanup delete failed
            # with that error, so orphaned files accumulated.
            httpx.request(
                "DELETE",
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

    def download(self, key: str, local_path: str | Path) -> Path:
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.stream("GET", self._obj_url(key), headers=self._headers,
                              timeout=300) as resp:
                resp.raise_for_status()
                expected = resp.headers.get("content-length")
                with target.open("wb") as fh:
                    for chunk in resp.iter_bytes(1024 * 1024):
                        fh.write(chunk)
                # A silently truncated stream would pass ingest (magic
                # bytes + ffprobe header) and die later at normalize —
                # fail here with a clear message instead.
                if expected is not None:
                    got = target.stat().st_size
                    if got != int(expected):
                        raise RuntimeError(
                            f"incomplete download for {key}: "
                            f"got {got} bytes, expected {expected}")
        except httpx.HTTPStatusError as exc:
            log.warning("supabase download failed for %s: %s %s",
                        key, exc.response.status_code, exc.response.text[:500])
            raise
        return target
