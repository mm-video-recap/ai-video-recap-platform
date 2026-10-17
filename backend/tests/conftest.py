"""
Pytest bootstrap.

Sets ALL environment BEFORE any backend.* import (Settings is lru-cached and
the DB engine caches per DATABASE_URL). Uses a throwaway sqlite file + local
storage so the suite runs with zero external services.

Run from the repo root:  backend/venv/bin/python -m pytest backend/tests -q
(`python -m` puts the repo root on sys.path so `import backend.*` works.)
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="recap_test_")

os.environ["ENV"] = "development"
os.environ["DEV_AUTH_BYPASS"] = "1"          # documented dev-only escape hatch
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["STORAGE_ROOT"] = f"{_TMP}/storage"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["REDIS_URL"] = "redis://localhost:6399/0"      # nothing listening
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6399/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6399/1"
os.environ["ADMIN_EMAILS"] = "admin@dev.local"
os.environ["WORKER_GATEWAY_TOKEN"] = "test-gateway-token"
os.environ["EMAIL_ENABLED"] = "0"
# Rate limits raised for the suite: all TestClient requests share one IP,
# so the production upload cap (10/minute) would otherwise make the suite
# flaky once the upload-test count grows. Production defaults are unchanged.
os.environ["RATE_LIMIT_DEFAULT"] = "10000/minute"
os.environ["RATE_LIMIT_UPLOAD"] = "10000/minute"

import pytest  # noqa: E402

from backend.config import get_settings  # noqa: E402

get_settings.cache_clear()
assert get_settings().DEV_AUTH_BYPASS is True

from backend.database import create_all, reset_engine_cache  # noqa: E402

reset_engine_cache()
create_all()

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers():
    def _headers(user: str = "u1") -> dict:
        return {"Authorization": f"Bearer dev-token-{user}"}
    return _headers


@pytest.fixture(scope="session")
def admin_headers(auth_headers):
    return auth_headers("admin@dev.local")


@pytest.fixture(scope="session")
def make_mp4_bytes():
    def _bytes(size: int = 2048) -> bytes:
        """Minimal fake mp4: valid ftyp magic so the ingestion sniffer accepts it."""
        head = b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00" + b"\x00" * 64
        return head + b"\x00" * max(0, size - len(head))
    return _bytes


@pytest.fixture()
def uploaded(client, auth_headers, make_mp4_bytes):
    """Upload a fake mp4 as a fresh unique user (dodges the 5/day fair-use
    cap across tests). Returns dict(video_id, job_id, headers, token)."""
    import uuid  # noqa: PLC0415
    from unittest import mock  # noqa: PLC0415

    user = f"up_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    # The fixture file is ftyp magic + zeros: real ffprobe cannot read
    # it, and ingest now rejects files ffprobe cannot read (corrupt /
    # truncated). Patch probe metadata for this fixture only.
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta):
        r = client.post("/api/videos/upload", files=files, headers=headers,
                        data={"gemini_key": "test-gemini",
                              "groq_key": "test-groq"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["video_id"] and body["job_id"]
    assert isinstance(body["estimated_seconds"], int)
    body["headers"] = headers
    body["token"] = f"dev-token-{user}"
    return body
