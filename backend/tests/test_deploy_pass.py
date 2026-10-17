"""
Regression tests for the 2026-10-15 deploy pass. Each test pins one fix:

1. CORS wildcard + credentials (B1/P0) — wildcards rejected, unlisted
   origins get no credentialed reflection.
2. /ready endpoint — DB/Redis checks, no leaked internals.
3. B15 — subtitle_language persisted on the Job.
4. B19 — upload size cap enforced before the whole file is written.
5. Download URLs built from the request host, not localhost API_BASE_URL.
6. Admin overview no longer exposes the absolute STORAGE_ROOT path.
7. Migration 001 stays in sync with models.py for the new columns.
"""
import re
from unittest import mock

import pytest


# ------------------------------------------------------------------ 1. CORS
def test_cors_rejects_wildcard():
    from backend.main import build_cors_options

    for bad in (["*"], ["https://*.pages.dev"],
                ["http://localhost:3000", "https://*.example.com"]):
        with pytest.raises(ValueError, match="EXACT origins"):
            build_cors_options(bad)

    opts = build_cors_options(["http://localhost:3000",
                               "https://myan-recap.pages.dev"])
    assert opts["allow_origins"] == ["http://localhost:3000",
                                     "https://myan-recap.pages.dev"]
    assert opts["allow_credentials"] is True
    # No regex-based origin matching may ever be configured.
    assert "allow_origin_regex" not in opts


def test_cors_preflight_unlisted_origin(client):
    # Unlisted origin (incl. a *.pages.dev subdomain that is NOT the exact
    # deployed domain) must NOT get a credentialed allow-origin reflection.
    # Starlette's 400 "Disallowed CORS origin" failure response still carries
    # a generic allow-credentials header, but WITHOUT allow-origin the
    # browser will not expose the response cross-origin — that is the
    # security property that matters.
    r = client.options(
        "/api/health",
        headers={"Origin": "https://evil.pages.dev",
                 "Access-Control-Request-Method": "GET"})
    assert r.status_code == 400
    assert r.headers.get("access-control-allow-origin") is None
    assert "Disallowed CORS origin" in r.text

    # Listed dev origin gets the exact reflection + credentials.
    r = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:3000",
                 "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert r.headers.get("access-control-allow-credentials") == "true"


# ------------------------------------------------------------------ 2. /ready
def test_ready_endpoint_shape_and_no_leaks(client):
    for path in ("/ready", "/api/ready"):
        r = client.get(path)
        # Test env: sqlite DB is up, Redis on :6399 is down -> degraded 503.
        assert r.status_code == 503, (path, r.text)
        body = r.json()
        assert body["status"] == "degraded"
        assert body["checks"] == {"database": "ok", "redis": "error"}
        # No internals: no hosts, ports, paths, or exception text.
        for leaked in ("localhost", "6399", "/tmp", "Traceback", "sqlite"):
            assert leaked not in r.text, (path, leaked)


def test_ready_database_down_reports_error(client, monkeypatch):
    """If the DB check itself fails, readiness reports database: error."""
    import backend.main as main_mod

    monkeypatch.setattr(main_mod, "_check_database", lambda: False)
    monkeypatch.setattr(main_mod, "_check_redis", lambda: True)
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"database": "error", "redis": "ok"}


# ------------------------------------------------------------------ 3. B15
def test_upload_persists_recap_prefs(client, auth_headers, make_mp4_bytes):
    import uuid

    user = f"prefs_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    # Fixture file is ftyp magic + zeros: real ffprobe cannot read it,
    # and ingest now rejects files ffprobe cannot read.
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta):
        r = client.post(
            "/api/videos/upload?subtitle_language=none",
            files=files, headers=headers,
            data={"gemini_key": "test-gemini", "groq_key": "test-groq"})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]

    r = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["subtitle_language"] == "none"


def test_upload_rejects_bad_subtitle_language(client, auth_headers, make_mp4_bytes):
    import uuid

    user = f"prefs_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    r = client.post("/api/videos/upload?subtitle_language=xx",
                    files=files, headers=headers)
    assert r.status_code == 422


def test_upload_defaults_subtitle_language(client, uploaded):
    r = client.get(f"/api/jobs/{uploaded['job_id']}",
                   headers=uploaded["headers"])
    assert r.status_code == 200
    assert r.json()["subtitle_language"] == "my"


# ------------------------------------------------------------------ 4. B19
def test_upload_oversized_rejected_413(client, auth_headers, make_mp4_bytes,
                                       monkeypatch):
    """Content-Length over the cap -> 413 before the file is processed."""
    import uuid

    from backend.api import routes_videos
    from backend.config import Settings

    tiny = Settings(MAX_UPLOAD_BYTES=100)
    monkeypatch.setattr(routes_videos, "get_settings", lambda: tiny)
    user = f"cap_{uuid.uuid4().hex[:8]}"
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    r = client.post("/api/videos/upload", files=files,
                    headers=auth_headers(user))
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower()


# ------------------------------------------------- 5. download URL host
def test_results_download_url_uses_request_host(client, uploaded):
    """Local download URLs come from the request host, NOT localhost:8000."""
    from backend.database import Job, Output, get_session_factory

    db = get_session_factory()()
    try:
        job = db.query(Job).filter_by(id=uploaded["job_id"]).one()
        job.status = "completed"
        job.result = {"summary": {"title": "T", "description": "",
                                  "summary_short": "", "summary_long": "",
                                  "key_points": [], "timeline": []},
                      "speech": {"transcript": []}, "highlights": []}
        db.add(Output(job_id=job.id, kind="recap_video",
                      storage_path=f"results/{job.id}/recap_final.mp4",
                      size_bytes=123))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/results/{uploaded['job_id']}",
                   headers=uploaded["headers"])
    assert r.status_code == 200, r.text
    url = r.json()["download_url"]
    assert url.startswith("http://testserver/api/results/"), url
    assert "localhost:8000" not in url


# ------------------------------------------------- 6. admin overview
def test_admin_overview_hides_storage_root(client, admin_headers):
    r = client.get("/api/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["storage"] == {"provider": "local"}
    assert "root" not in r.json()["storage"]
    assert "/tmp" not in r.text and "recap_test_" not in r.text


# ------------------------------------------------- 7. migration sync
def test_migration_matches_models_for_new_columns():
    from pathlib import Path

    sql = Path("supabase/migrations/001_init.sql").read_text()
    assert "subtitle_language" in sql
    assert "recap_style" in sql
    # bigint for size_bytes (2 GiB cap is 1 over Postgres int4 max).
    assert re.search(r"size_bytes\s+bigint", sql)
    assert not re.search(r"size_bytes\s+int[,\s]", sql)
    # Still run-once by design (documented): only the extension uses IF NOT EXISTS.
    assert sql.count("IF NOT EXISTS") == 1
