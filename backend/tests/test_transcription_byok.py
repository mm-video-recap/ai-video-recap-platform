"""Tests: normalize scale cap, Gemini transcription (chunked), BYOK key
vault, speech provider routing, transcription prefs persistence."""
import io
import json
import subprocess
import wave

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


def test_keyvault_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet

    from backend.security.keyvault import decrypt_key, encrypt_key

    monkeypatch.setenv("USER_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt_key("sk-secret-abc")
    assert token != "sk-secret-abc"
    assert decrypt_key(token) == "sk-secret-abc"


def test_keyvault_missing_env(monkeypatch):
    from backend.security.keyvault import encrypt_key

    monkeypatch.delenv("USER_KEY_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        encrypt_key("x")


def test_keyvault_falls_back_to_supabase_key(monkeypatch):
    from backend.security.keyvault import decrypt_key, encrypt_key

    monkeypatch.delenv("USER_KEY_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "service-role-key-for-tests")
    token = encrypt_key("sk-secret-abc")
    assert decrypt_key(token) == "sk-secret-abc"
    # A different SUPABASE_KEY cannot decrypt (derivation is keyed).
    monkeypatch.setenv("SUPABASE_KEY", "a-different-service-key")
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        decrypt_key(token)


def test_keyvault_wrong_key(monkeypatch):
    from cryptography.fernet import Fernet

    from backend.security.keyvault import decrypt_key, encrypt_key

    monkeypatch.setenv("USER_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = encrypt_key("sk-secret-abc")
    monkeypatch.setenv("USER_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        decrypt_key(token)


def test_speech_routes_user_chosen_provider(monkeypatch):
    import asyncio

    from backend.agents.agent03_speech import SpeechAgent

    seen = {}

    class _Manager:
        async def transcribe_with(self, provider, audio, *, key=None):
            seen["provider"] = provider
            seen["key"] = key
            return ({"transcript": [{"start": 0, "end": 1, "text": "hi"}]}, provider)

        async def transcribe(self, audio):
            raise AssertionError("chain must not run for a user-chosen provider")

    agent = SpeechAgent(provider_manager=_Manager())
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(b"RIFF")
        tmp = tf.name
    out = agent.transcribe(tmp, "j1", provider="groq", key="user-groq-key")
    assert seen == {"provider": "groq", "key": "user-groq-key"}
    assert out["transcript"][0]["text"] == "hi"


def test_persist_ingestion_stores_transcription_prefs():
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
                      transcription_provider="groq",
                      transcription_key_enc="ENC-CIPHERTEXT")
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["transcription_provider"] == "groq"
    assert video.meta["transcription_key_enc"] == "ENC-CIPHERTEXT"
    assert "sk-" not in json.dumps(video.meta)


def test_upload_with_user_key_stores_ciphertext(client, auth_headers, make_mp4_bytes, monkeypatch):
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
            "/api/videos/upload?transcription_provider=groq",
            files=files, headers=headers,
            data={"transcription_key": "sk-user-groq-key"})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    video_id = r.json()["video_id"]
    r = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert r.status_code == 200
    # The job endpoint does not expose video.meta; verify via the DB
    # through the app's own session factory instead.
    from backend.database import Video, get_session_factory

    db = get_session_factory()()
    try:
        video = db.query(Video).filter_by(id=video_id).one()
        assert video.meta["transcription_provider"] == "groq"
        enc = video.meta["transcription_key_enc"]
        assert enc and "sk-user-groq-key" not in enc
        from backend.security.keyvault import decrypt_key

        assert decrypt_key(enc) == "sk-user-groq-key"
    finally:
        db.close()


def test_gemini_transcription_retries_on_503(monkeypatch):
    """A transient 503 (model high demand) must be retried per chunk,
    not fail the whole speech stage on first attempt."""
    import asyncio
    import wave as _wave

    from backend.ai_provider.manager import GeminiProvider, ProviderError

    calls = {"n": 0}

    class _FakeResp:
        def __init__(self, status):
            self.status_code = status
            self.text = '{"error": {"code": 503, "message": "high demand"}}'

    async def _fake_generate(self, audio_bytes, prompt):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderError("503 high demand", status=503, retryable=True)
        return '{"segments": [{"start": 0, "end": 1, "text": "hi"}]}'

    monkeypatch.setattr(GeminiProvider, "_generate_with_audio", _fake_generate)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr("asyncio.sleep", lambda s: _real_sleep(0))
    # Build a tiny valid WAV so chunking works.
    import io as _io
    buf = _io.BytesIO()
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
