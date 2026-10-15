"""
Local-disk storage backend.

Layout (mirrors the cloud bucket layout):
    <STORAGE_ROOT>/uploads | processing | results | temporary | thumbnails | reports
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from backend.storage.base import StorageBackend

log = logging.getLogger("storage.local")

BUCKETS = ("uploads", "processing", "results", "temporary", "thumbnails", "reports")


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        for bucket in BUCKETS:
            (self.root / bucket).mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Guard against path traversal: keys are always relative.
        safe = Path(key).as_posix().lstrip("/")
        target = (self.root / safe).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError(f"unsafe storage key: {key!r}")
        return target

    def put(self, local_path: str | Path, key: str) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # The rendering agent already writes its output under
        # <STORAGE_ROOT>/results/<job_id>/... — copying it onto itself
        # raises shutil.SameFileError. A no-op put is correct here.
        try:
            if Path(local_path).resolve() == target:
                return key
        except OSError:
            pass
        shutil.copyfile(local_path, target)
        log.debug("stored %s -> %s", local_path, target)
        return key

    def get_url(self, key: str, expires_sec: int = 3600) -> str:
        # Local dev: expose as a file path the API can serve / hand to ffmpeg.
        return str(self._resolve(key))

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except OSError as exc:
            log.warning("delete failed for %s: %s", key, exc)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def absolute(self, key: str) -> Path:
        return self._resolve(key)
