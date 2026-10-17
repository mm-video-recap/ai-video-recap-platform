"""Tests: per-user AI keys (BYOK) for summary / vision / translation.

When the user supplies their own Gemini/Groq keys, the job must spend
the user's own quota (owner keys never used for that provider). Empty
keys -> owner (env) keys, as before. Keys are stored encrypted only.
"""
import json


def test_user_keys_from_prefs_decrypts(monkeypatch):
    import backend.celery_app.tasks as tasks

    monkeypatch.setattr(
        "backend.security.keyvault.decrypt_key",
        lambda enc: {"ENC-G": "user-gemini", "ENC-Q": "user-groq"}[enc])
    out = tasks._user_keys_from_prefs(
        {"gemini_key_enc": "ENC-G", "groq_key_enc": "ENC-Q"})
    assert out == {"gemini": ["user-gemini"], "groq": ["user-groq"]}


def test_user_keys_from_prefs_empty_without_keys():
    import backend.celery_app.tasks as tasks

    assert tasks._user_keys_from_prefs({}) == {}
    assert tasks._user_keys_from_prefs({"gemini_key_enc": ""}) == {}


def test_user_keys_from_prefs_skips_undecryptable(monkeypatch):
    import backend.celery_app.tasks as tasks

    def _boom(enc):
        raise RuntimeError("bad ciphertext")

    monkeypatch.setattr("backend.security.keyvault.decrypt_key", _boom)
    assert tasks._user_keys_from_prefs({"gemini_key_enc": "ENC-G"}) == {}


def test_provider_manager_user_keys_override(monkeypatch):
    from backend.ai_provider.manager import ProviderManager
    from backend.config import Settings

    monkeypatch.setenv("GEMINI_API_KEY", "owner-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "owner-groq")
    manager = ProviderManager(Settings(), user_keys={
        "gemini": ["user-gemini"], "groq": ["user-groq"]})
    assert manager.providers["gemini"]._keys == ["user-gemini"]
    assert manager.providers["groq"]._keys() == ["user-groq"]


def test_provider_manager_falls_back_to_owner_keys(monkeypatch):
    from backend.ai_provider.manager import ProviderManager
    from backend.config import Settings

    monkeypatch.setenv("GEMINI_API_KEY", "owner-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "owner-groq")
    manager = ProviderManager(Settings())
    assert manager.providers["gemini"]._keys == ["owner-gemini"]
    assert manager.providers["groq"]._keys() == ["owner-groq"]


def test_persist_ingestion_stores_ai_keys():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.agents.agent01_ingestion import IngestionResult, persist_ingestion
    from backend.database import Base, Job, User, Video

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(User(id="u1", email="u1@dev.local"))
    db.commit()
    res = IngestionResult(
        ok=True, job_id="j1", video_id="v1", container="mp4",
        metadata={"original_name": "a.mp4", "duration_sec": 10.0,
                  "size_bytes": 100, "sha256_prefix": "ab"})
    persist_ingestion(db, res, user_id="u1",
                      storage_path="uploads/v1/original.mp4",
                      gemini_key_enc="ENC-G", groq_key_enc="ENC-Q")
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["gemini_key_enc"] == "ENC-G"
    assert video.meta["groq_key_enc"] == "ENC-Q"
    assert "sk-" not in json.dumps(video.meta)


def test_upload_with_ai_keys_stores_ciphertext(client, auth_headers, make_mp4_bytes, monkeypatch):
    import uuid
    from unittest import mock

    from cryptography.fernet import Fernet

    monkeypatch.setenv("USER_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    user = f"byok_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta):
        r = client.post(
            "/api/videos/upload",
            files=files, headers=headers,
            data={"gemini_key": "sk-user-gemini", "groq_key": "gsk-user-groq"})
    assert r.status_code == 201, r.text
    video_id = r.json()["video_id"]
    from backend.database import Video, get_session_factory
    from backend.security.keyvault import decrypt_key

    db = get_session_factory()()
    try:
        video = db.query(Video).filter_by(id=video_id).one()
        enc_g = video.meta["gemini_key_enc"]
        enc_q = video.meta["groq_key_enc"]
        assert enc_g and "sk-user-gemini" not in enc_g
        assert enc_q and "gsk-user-groq" not in enc_q
        assert decrypt_key(enc_g) == "sk-user-gemini"
        assert decrypt_key(enc_q) == "gsk-user-groq"
    finally:
        db.close()


def test_translate_segments_passes_user_keys(monkeypatch):
    import backend.celery_app.tasks as tasks

    seen: dict = {}

    class _Manager:
        def __init__(self, settings, user_keys=None):
            seen["user_keys"] = user_keys

        async def complete(self, task, prompt, **kw):
            return (json.dumps({"segments": [{"text": "မင်္ဂလာပါ"}]}), "gemini")

    monkeypatch.setattr("backend.ai_provider.manager.ProviderManager", _Manager)
    segments = [{"start": 0, "end": 2, "text": "Hello"}]
    out, ok = tasks._translate_segments(
        object(), segments, "my", "en", user_keys={"gemini": ["user-gemini"]})
    assert ok is True
    assert [s["text"] for s in out] == ["မင်္ဂလာပါ"]
    assert seen["user_keys"] == {"gemini": ["user-gemini"]}


def test_translate_text_passes_user_keys(monkeypatch):
    import backend.celery_app.tasks as tasks

    seen: dict = {}

    class _Manager:
        def __init__(self, settings, user_keys=None):
            seen["user_keys"] = user_keys

        async def complete(self, task, prompt, **kw):
            return ("မင်္ဂလာပါ", "gemini")

    monkeypatch.setattr("backend.ai_provider.manager.ProviderManager", _Manager)
    out, ok = tasks._translate_text(
        object(), "Hello", "my", "en", user_keys={"groq": ["user-groq"]})
    assert (out, ok) == ("မင်္ဂလာပါ", True)
    assert seen["user_keys"] == {"groq": ["user-groq"]}
