"""Tests: per-key verify/delete icons backend + both-keys gate + owner.

Rules (user order 2026-10-17):
- Every key field has show / verify / delete (frontend icons; this file
  covers the backend that powers verify + the gate).
- Non-owner users MUST bring BOTH their own Gemini + Groq keys to
  upload; the server (env) keys are NOT spent on them.
- Only the single OWNER_EMAIL account may use the server keys
  (upload without user keys succeeds for the owner only).
"""
import uuid
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from backend.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_owner(monkeypatch, email):
    from backend.config import get_settings

    monkeypatch.setenv("OWNER_EMAIL", email)
    get_settings.cache_clear()


def _upload(client, headers, files, data=None):
    return client.post("/api/videos/upload", files=files, headers=headers,
                       data=data or {})


def _fake_files(make_mp4_bytes):
    return {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}


def _fake_meta():
    return ({"duration_sec": 8.0, "video_codec": "h264",
             "audio_codec": "aac", "has_audio": True,
             "width": 640, "height": 360, "fps": 30.0}, True)


# ------------------------------------------------------------- verify endpoint

def test_verify_gemini_valid(monkeypatch, client, auth_headers):
    import backend.api.routes_keys as routes_keys

    monkeypatch.setattr(routes_keys, "_verify_gemini_key",
                        lambda k: (True, "ok"))
    r = client.post("/api/keys/verify",
                    json={"provider": "gemini", "key": "sk-test"},
                    headers=auth_headers("u1"))
    assert r.status_code == 200
    assert r.json() == {"valid": True, "reason": "ok"}


def test_verify_groq_invalid(monkeypatch, client, auth_headers):
    import backend.api.routes_keys as routes_keys

    monkeypatch.setattr(routes_keys, "_verify_groq_key",
                        lambda k: (False, "invalid"))
    r = client.post("/api/keys/verify",
                    json={"provider": "groq", "key": "gsk-bad"},
                    headers=auth_headers("u1"))
    assert r.status_code == 200
    assert r.json() == {"valid": False, "reason": "invalid"}


def test_verify_requires_auth(client):
    r = client.post("/api/keys/verify",
                    json={"provider": "gemini", "key": "x"})
    assert r.status_code == 401


def test_verify_bad_provider(client, auth_headers):
    r = client.post("/api/keys/verify",
                    json={"provider": "openai", "key": "x"},
                    headers=auth_headers("u1"))
    assert r.status_code == 422


def test_verify_empty_key(client, auth_headers):
    r = client.post("/api/keys/verify",
                    json={"provider": "gemini", "key": ""},
                    headers=auth_headers("u1"))
    assert r.status_code == 422


class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeClient:
    status_code = 200

    def __init__(self, *a, **kw):
        pass

    def get(self, url, headers=None):
        return _FakeResp(self.status_code)


def test_verify_gemini_helper_statuses(monkeypatch):
    import backend.api.routes_keys as routes_keys

    monkeypatch.setattr(routes_keys.httpx, "Client", _FakeClient)
    _FakeClient.status_code = 200
    assert routes_keys._verify_gemini_key("k") == (True, "ok")
    _FakeClient.status_code = 400
    assert routes_keys._verify_gemini_key("k") == (False, "invalid")
    _FakeClient.status_code = 429
    assert routes_keys._verify_gemini_key("k") == (True, "quota")
    _FakeClient.status_code = 500
    assert routes_keys._verify_gemini_key("k") == (False, "error")


def test_verify_groq_helper_statuses(monkeypatch):
    import backend.api.routes_keys as routes_keys

    monkeypatch.setattr(routes_keys.httpx, "Client", _FakeClient)
    _FakeClient.status_code = 200
    assert routes_keys._verify_groq_key("k") == (True, "ok")
    _FakeClient.status_code = 401
    assert routes_keys._verify_groq_key("k") == (False, "invalid")
    _FakeClient.status_code = 429
    assert routes_keys._verify_groq_key("k") == (True, "quota")


# ------------------------------------------------------------- upload key gate

def test_upload_nonowner_requires_both_keys(client, auth_headers, make_mp4_bytes):
    user = f"gate_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=_fake_meta()):
        # No keys at all.
        r = _upload(client, headers, _fake_files(make_mp4_bytes))
        assert r.status_code == 400
        assert "both" in r.json()["detail"].lower()
        # Only Gemini.
        r = _upload(client, headers, _fake_files(make_mp4_bytes),
                    data={"gemini_key": "g1"})
        assert r.status_code == 400
        # Only Groq.
        r = _upload(client, headers, _fake_files(make_mp4_bytes),
                    data={"groq_key": "q1"})
        assert r.status_code == 400


def test_upload_nonowner_with_both_keys_ok(client, auth_headers, make_mp4_bytes):
    user = f"gate_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=_fake_meta()), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    return_value=True):
        r = _upload(client, headers, _fake_files(make_mp4_bytes),
                    data={"gemini_key": "g1", "groq_key": "q1"})
    assert r.status_code == 201, r.text


def test_upload_owner_may_use_server_keys(client, auth_headers, make_mp4_bytes,
                                          monkeypatch):
    _set_owner(monkeypatch, "owner@dev.local")
    headers = auth_headers("owner@dev.local")
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=_fake_meta()), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    return_value=True):
        # Owner uploads with NO user keys -> server keys apply.
        r = _upload(client, headers, _fake_files(make_mp4_bytes))
    assert r.status_code == 201, r.text


def test_upload_owner_email_must_match_exactly(client, auth_headers,
                                               make_mp4_bytes, monkeypatch):
    _set_owner(monkeypatch, "owner@dev.local")
    headers = auth_headers("someone-else@dev.local")
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=_fake_meta()):
        r = _upload(client, headers, _fake_files(make_mp4_bytes))
    assert r.status_code == 400


# ------------------------------------------------------------- /me is_owner

def test_me_returns_is_owner(client, auth_headers, monkeypatch):
    _set_owner(monkeypatch, "owner@dev.local")
    r = client.get("/api/auth/me", headers=auth_headers("owner@dev.local"))
    assert r.status_code == 200
    assert r.json()["is_owner"] is True
    r = client.get("/api/auth/me", headers=auth_headers("other@dev.local"))
    assert r.status_code == 200
    assert r.json()["is_owner"] is False
