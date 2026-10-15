"""Storage backend interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Minimal object-storage interface all backends implement."""

    name: str = "base"

    @abstractmethod
    def put(self, local_path: str | Path, key: str) -> str:
        """Upload a local file to `key`. Returns the stored key."""

    @abstractmethod
    def get_url(self, key: str, expires_sec: int = 3600) -> str:
        """Public/download URL for a stored key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a stored key (best effort)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check a stored key exists."""
