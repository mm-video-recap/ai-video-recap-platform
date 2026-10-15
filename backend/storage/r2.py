"""
Cloudflare R2 storage backend (S3-compatible, via boto3).

Optional: boto3 is imported lazily. Without credentials the manager falls
back to local storage with a warning — the app never crashes.
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.storage.base import StorageBackend

log = logging.getLogger("storage.r2")


class R2Storage(StorageBackend):
    name = "r2"

    def __init__(self, account_id: str, access_key: str, secret_key: str,
                 bucket_uploads: str, bucket_results: str, bucket_temp: str):
        try:
            import boto3  # noqa: PLC0415 - optional dependency
        except Exception as exc:
            raise RuntimeError("boto3 is not installed; cannot use R2 storage") from exc
        if not (account_id and access_key and secret_key):
            raise RuntimeError("R2 credentials missing; cannot use R2 storage")
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._buckets = {
            "uploads": bucket_uploads,
            "results": bucket_results,
            "temporary": bucket_temp,
        }

    def _bucket_for(self, key: str) -> str:
        top = Path(key).parts[0] if Path(key).parts else ""
        return self._buckets.get(top, self._buckets["temporary"])

    def put(self, local_path: str | Path, key: str) -> str:
        self._client.upload_file(str(local_path), self._bucket_for(key), key)
        return key

    def get_url(self, key: str, expires_sec: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_for(key), "Key": key},
            ExpiresIn=expires_sec,
        )

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket_for(key), Key=key)
        except Exception as exc:  # best effort
            log.warning("r2 delete failed for %s: %s", key, exc)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket_for(key), Key=key)
            return True
        except Exception:
            return False
