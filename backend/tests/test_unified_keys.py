"""Tests: unified per-user AI keys + recap_style removal.

One key entry (Settings -> My API Keys) for everything. Keys travel
as Celery task kwargs (in-memory only) and are NEVER written to the
database. recap_style is gone from the API and the Job response.
"""
import io
import json
import subprocess
import wave
from unittest import mock

import pytest

from backend.agents.agent02_processing import ProcessingAgent


def _make_vertical_clip(path, w=1440, h=2560, dur=2):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"color=c=0x1a2b4a:s={w}x{h}:d={dur}:r=30",
           "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-shortest", str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _probe_dims(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    w, h = (proc.stdout or "0,0").strip().split(",")
    return int(w), int(h)


def test_normalize_caps_long_side_at_1280(tmp_path):
    src = tmp_path / "vertical.mp4"
    _make_vertical_clip(src)
    agent = ProcessingAgent(tmp_path / "processing")
    res = agent.process(str(src), "j1")
    assert res.ok, res.errors
    w, h = _probe_dims(res.normalized_path)
    assert max(w, h) <= 1280, (w, h)
    assert (w, h) == (720, 1280)


def _make_wav(path, seconds=3, rate=16000):
    import struct

    n = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *([0] * n)))


def test_gemini_transcribe_chunks_and_offsets(tmp_path, monkeypatch):
    import httpx

    from backend.ai_provider.manager import GeminiProvider
    from backend.config import get_settings

    wav = tmp_path / "a.wav"
    _make_wav(wav, seconds=3)

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        seg = {"segments": [{"start": 0.0, "end": 1.0, "text": f"chunk{calls['n']}"}]}
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps(seg)}]}}]}
        return httpx.Response(200, json=body)

    settings = get_settings()
    provider = GeminiProvider(settings, transport=httpx.MockTransport(handler),
                              keys=["user-key-123"])
    provider._TRANSCRIBE_CHUNK_SEC = 1  # 3s audio -> 3 chunks
    import asyncio

    out = asyncio.run(provider.transcribe(wav))
    assert calls["n"] == 3
    assert [s["text"] for s in out["transcript"]] == ["chunk1", "chunk2", "chunk3"]
    assert [s["start"] for s in out["transcript"]] == [0.0, 1.0, 2.0]
    assert out["engine"] == "gemini"


def test_gemini_transcribe_requires_key(monkeypatch):
    import asyncio

    from backend.ai_provider.manager import GeminiProvider, ProviderError
    from backend.config import get_settings

    provider = GeminiProvider(get_settings(), keys=[])
    with pytest.raises(ProviderError, match="no API keys"):
        asyncio.run(provider.transcribe("/tmp/nope.wav"))


def test_gemini_transcription_retries_on_503(monkeypatch):
    """A transient 503 (model high demand) must be retried per chunk,
    not fail the whole speech stage on first attempt."""
    import asyncio
    import wave as _wave

    from backend.ai_provider.manager import GeminiProvider, ProviderError

    calls = {"n": 0}

    async def _fake_generate(self, audio_bytes, prompt):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderError("503 high demand", status=503, retryable=True)
        return '{"segments": [{"start": 0, "end": 1, "text": "hi"}]}'

    monkeypatch.setattr(GeminiProvider, "_generate_with_audio", _fake_generate)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr("asyncio.sleep", lambda s: _real_sleep(0))
    # Build a tiny valid WAV so chunking works.
    buf = io.BytesIO()
    with _wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    wav_path = "/tmp/test_retry_503.wav"
    open(wav_path, "wb").write(buf.getvalue())

    import os
    os.environ.setdefault("GEMINI_API_KEY", "test-key")
    provider = GeminiProvider.__new__(GeminiProvider)
    provider._keys = ["k"]
    from backend.config import Settings
    provider.settings = Settings()
    out = asyncio.run(provider.transcribe(wav_path))
    assert out["transcript"] == [{"start": 0, "end": 1, "text": "hi"}]
    assert calls["n"] == 3


# ---------------------------------------------------------------- unified keys

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


def test_speech_chain_includes_gemini():
    from backend.ai_provider.manager import TASK_ROUTES

    assert TASK_ROUTES["speech"] == ["groq", "gemini", "huggingface"]


def test_speech_agent_uses_chain(monkeypatch):
    import tempfile

    import backend.agents.agent03_speech as speech_mod
    from backend.agents.agent03_speech import SpeechAgent

    # Force the provider chain even if faster-whisper is installed.
    monkeypatch.setattr(speech_mod, "_FASTER_WHISPER_AVAILABLE", False)

    class _Manager:
        async def transcribe(self, audio):
            return ({"transcript": [{"start": 0, "end": 1, "text": "hi"}]}, "groq")

    agent = SpeechAgent(provider_manager=_Manager())
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(b"RIFF")
        tmp = tf.name
    out = agent.transcribe(tmp, "j1")
    assert out["transcript"][0]["text"] == "hi"
    assert out["degraded"] is False


def test_upload_forwards_user_keys_to_pipeline(client, auth_headers, make_mp4_bytes):
    import uuid

    user = f"keys_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    seen = {}

    def _fake_enqueue(video_id, job_id, priority=3, user_keys=None):
        seen["user_keys"] = user_keys
        return True

    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    side_effect=_fake_enqueue):
        r = client.post(
            "/api/videos/upload",
            files=files, headers=headers,
            data={"gemini_key": "sk-user-gemini", "groq_key": "gsk-user-groq"})
    assert r.status_code == 201, r.text
    assert seen["user_keys"] == {"gemini": ["sk-user-gemini"], "groq": ["gsk-user-groq"]}
    # No key material persisted in the DB.
    from backend.database import Video, get_session_factory

    db = get_session_factory()()
    try:
        video = db.query(Video).filter_by(id=r.json()["video_id"]).one()
        assert "sk-user-gemini" not in json.dumps(video.meta)
        assert "gsk-user-groq" not in json.dumps(video.meta)
        assert "gemini_key" not in video.meta
        assert "groq_key" not in video.meta
        assert "transcription_key_enc" not in video.meta
    finally:
        db.close()


def test_upload_without_keys_rejected_for_nonowner(client, auth_headers, make_mp4_bytes):
    """Non-owner uploads without BOTH user keys are rejected (key gate);
    the pipeline is never enqueued. Owner behaviour is covered in
    test_key_management.py."""
    import uuid

    user = f"keys_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    seen = {"called": False}

    def _fake_enqueue(video_id, job_id, priority=3, user_keys=None):
        seen["called"] = True
        seen["user_keys"] = user_keys
        return True

    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    side_effect=_fake_enqueue):
        r = client.post("/api/videos/upload", files=files, headers=headers)
    assert r.status_code == 400
    assert seen["called"] is False


def test_persist_ingestion_stores_no_key_material():
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
                      storage_path="uploads/v1/original.mp4")
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert "gemini_key" not in video.meta
    assert "groq_key" not in video.meta
    assert "transcription_key_enc" not in video.meta
    assert "key" not in json.dumps(video.meta)


def test_next_forwards_user_keys(monkeypatch):
    import backend.celery_app.tasks as tasks

    monkeypatch.setattr(tasks, "broker_reachable", lambda: True)
    seen = {}

    class _Fn:
        def apply_async(self, args=None, kwargs=None, priority=None):
            seen.update(args=args, kwargs=kwargs, priority=priority)

    assert tasks._next(_Fn(), "j1", 3, user_keys={"gemini": ["k"]}) is True
    assert seen["kwargs"] == {"user_keys": {"gemini": ["k"]}}
    seen.clear()
    assert tasks._next(_Fn(), "j1", 3) is True
    assert seen["kwargs"] == {}


def test_enqueue_pipeline_forwards_user_keys(monkeypatch):
    import backend.celery_app.tasks as tasks

    monkeypatch.setattr(tasks, "broker_reachable", lambda: True)
    seen = {}

    def _fake_apply_async(args=None, kwargs=None, queue=None, priority=None):
        seen.update(args=args, kwargs=kwargs, queue=queue)

    monkeypatch.setattr(tasks.ingest_video, "apply_async", _fake_apply_async)
    assert tasks.enqueue_pipeline("v1", "j1", user_keys={"groq": ["g"]}) is True
    assert seen["kwargs"] == {"user_keys": {"groq": ["g"]}}
    assert seen["queue"] == "video_upload_queue"


def test_build_pipeline_carries_user_keys():
    import backend.celery_app.tasks as tasks

    pipe = tasks.build_pipeline("v1", "j1", user_keys={"gemini": ["k"]})
    sigs = pipe.tasks
    assert len(sigs) == 5
    for sig in sigs[:4]:
        assert sig.kwargs.get("user_keys") == {"gemini": ["k"]}
    # send_notification needs no keys.
    assert "user_keys" not in sigs[4].kwargs


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


def test_job_response_has_no_recap_style(client, auth_headers, make_mp4_bytes):
    import uuid

    user = f"nostyle_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    return_value=True):
        r = client.post("/api/videos/upload", files=files, headers=headers,
                        data={"gemini_key": "test-gemini",
                              "groq_key": "test-groq"})
    assert r.status_code == 201, r.text
    r = client.get(f"/api/jobs/{r.json()['job_id']}", headers=headers)
    assert r.status_code == 200
    assert "recap_style" not in r.json()
    assert r.json()["subtitle_language"] == "my"
