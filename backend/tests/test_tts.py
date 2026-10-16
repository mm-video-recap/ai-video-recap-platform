"""Tests: TTS narration (Edge/Gemini) + voice prefs + render integration."""
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend.agents.agent07_rendering import RenderingAgent
from backend.agents.agent_tts import (
    fit_narration_to_duration,
    replace_audio,
    split_text,
    synthesize_narration,
    validate_tts_prefs,
)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE),
                                  reason="ffmpeg/ffprobe not installed")


def _probe_streams(path):
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    return set((proc.stdout or "").split())


def _duration(path):
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    return float((proc.stdout or "0").strip() or 0)


def _make_sine_wav(path, dur: float):
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(path)],
        capture_output=True, timeout=60, check=True)


def _make_source(path, with_audio: bool, dur: int = 4):
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i",
           f"color=c=0x1a2b4a:s=640x360:d={dur}:r=30"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={dur}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def test_validate_tts_prefs():
    validate_tts_prefs("edge", "thiha", 1.0, 0)
    validate_tts_prefs("edge", "nilar", 1.3, -10)
    validate_tts_prefs("gemini", "Kore", 0.8, 5)
    for bad in [("edge", "Kore", 1.0, 0), ("gemini", "thiha", 1.0, 0),
                ("edge", "thiha", 2.5, 0), ("edge", "thiha", 1.0, 25),
                ("other", "thiha", 1.0, 0)]:
        with pytest.raises(ValueError):
            validate_tts_prefs(*bad)


def test_split_text_keeps_sentences():
    text = " ".join(f"Sentence number {i} here." for i in range(100))
    chunks = split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    assert " ".join(chunks) == text


@needs_ffmpeg
def test_fit_narration_speeds_up_and_pads(tmp_path):
    wav = tmp_path / "n.wav"
    _make_sine_wav(wav, 5.0)
    fast = fit_narration_to_duration(wav, 3.0, tmp_path)
    assert fast is not None
    assert abs(_duration(fast) - 3.0) < 0.3
    padded = fit_narration_to_duration(wav, 8.0, tmp_path)
    assert padded is not None
    assert abs(_duration(padded) - 8.0) < 0.3


@needs_ffmpeg
def test_replace_audio_keeps_video_length(tmp_path):
    video = tmp_path / "v.mp4"
    _make_source(video, with_audio=True, dur=4)
    narr = tmp_path / "n.wav"
    _make_sine_wav(narr, 4.0)
    out = tmp_path / "out.mp4"
    assert replace_audio(video, narr, out)
    assert "audio" in _probe_streams(out)
    assert abs(_duration(out) - 4.0) < 0.3


@needs_ffmpeg
def test_render_with_narration_adds_audio_to_video_only_source(tmp_path, monkeypatch):
    """Video-only source + TTS narration -> recap HAS an audio track."""
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=False, dur=4)
    narr = tmp_path / "mock_narration.wav"
    _make_sine_wav(narr, 3.0)

    def _fake_synthesize(text, provider, voice, rate, pitch, workdir, settings=None):
        assert text.strip()
        return narr

    monkeypatch.setattr("backend.agents.agent_tts.synthesize_narration",
                        _fake_synthesize)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(
        src, [{"start": 0, "end": 2}], [{"start": 0, "end": 2, "text": "hi"}],
        "T", "j-narr", intro_text="Intro", outro_text="Thanks",
        narration_text="This is a test narration of the recap.",
        tts_provider="edge", tts_voice="thiha", tts_rate=1.0, tts_pitch=0)
    assert res.ok, res.errors
    assert "audio" in _probe_streams(res.video_path)


@needs_ffmpeg
def test_render_falls_back_to_gemini_when_edge_unreachable(tmp_path, monkeypatch):
    """Edge TTS down -> Gemini TTS used instead of silently keeping audio."""
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=False, dur=4)
    narr = tmp_path / "gemini_narration.wav"
    _make_sine_wav(narr, 3.0)

    def _fake_synthesize(text, provider, voice, rate, pitch, workdir, settings=None):
        if provider == "edge":
            return None  # simulate unreachable Edge endpoint
        assert provider == "gemini" and voice == "Charon"  # thiha -> Charon
        return narr

    monkeypatch.setattr("backend.agents.agent_tts.synthesize_narration",
                        _fake_synthesize)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(
        src, [{"start": 0, "end": 2}], [{"start": 0, "end": 2, "text": "hi"}],
        "T", "j-fallback", intro_text="Intro", outro_text="Thanks",
        narration_text="Test narration.",
        tts_provider="edge", tts_voice="thiha", tts_rate=1.0, tts_pitch=0)
    assert res.ok, res.errors
    assert "audio" in _probe_streams(res.video_path)
    assert any("Gemini voice Charon" in w for w in res.warnings)


@needs_ffmpeg
def test_render_without_narration_unchanged(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=True, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(src, [{"start": 0, "end": 2}],
                       [{"start": 0, "end": 2, "text": "hi"}],
                       "T", "j-orig", intro_text="Intro", outro_text="Thanks")
    assert res.ok, res.errors
    assert "audio" in _probe_streams(res.video_path)


def test_synthesize_narration_uses_chunks(tmp_path, monkeypatch):
    """Chunked synthesis merges parts into one WAV (Edge path mocked)."""
    import backend.agents.agent_tts as tts_mod

    calls = []

    class _FakeCommunicate:
        def __init__(self, text, voice, rate=None, pitch=None):
            calls.append((text, voice, rate, pitch))

        async def save(self, path):
            import shutil as _shutil
            _shutil.copyfile(str(tmp_path / "seed.wav"), path)

    _make_sine_wav(tmp_path / "seed.wav", 1.0)
    # seed is a WAV; edge-tts saves MP3 — the merge re-encodes via ffmpeg,
    # so a WAV seed works for the merge step.
    monkeypatch.setattr("edge_tts.Communicate", _FakeCommunicate)
    long_text = " ".join(f"Sentence number {i} here." for i in range(100))
    out = synthesize_narration(long_text, "edge", "thiha", 1.1, -5,
                               tmp_path / "work")
    assert out is not None and out.exists()
    assert len(calls) > 1
    assert all(c[1] == "my-MM-ThihaNeural" for c in calls)
    assert all(c[2] == "+10%" for c in calls)
    assert all(c[3] == "-5Hz" for c in calls)


def test_synthesize_gemini_writes_wav(tmp_path, monkeypatch):
    import asyncio
    import base64
    import wave

    import httpx

    import backend.agents.agent_tts as tts_mod

    pcm = b"\x00\x00" * 24000  # 1s of silence at 24kHz mono 16-bit

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, params=None, json=None):
            assert "gemini-2.5-flash-preview-tts" in url
            assert json["generationConfig"]["speechConfig"]["voiceConfig"][
                "prebuiltVoiceConfig"]["voiceName"] == "Kore"
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    settings = SimpleNamespace(gemini_keys=["fake-key"])
    out = tmp_path / "g.wav"
    asyncio.run(tts_mod._synthesize_gemini("Hello", "Kore", settings, out))
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 24000
        assert wf.getsampwidth() == 2
        assert wf.getnframes() == 24000


def test_persist_ingestion_stores_voice_prefs():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.agents.agent01_ingestion import IngestionResult, persist_ingestion
    from backend.database import Base, Job, Video

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(__import__("backend.database", fromlist=["User"]).User(
        id="u1", email="u1@dev.local"))
    db.commit()
    res = IngestionResult(
        ok=True, job_id="j1", video_id="v1", container="mp4",
        metadata={"original_name": "a.mp4", "duration_sec": 10.0,
                  "size_bytes": 100, "sha256_prefix": "ab"})
    persist_ingestion(db, res, user_id="u1",
                      storage_path="uploads/v1/original.mp4",
                      voice_mode="tts", tts_provider="edge",
                      tts_voice="nilar", tts_rate=1.2, tts_pitch=-5)
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["voice_mode"] == "tts"
    assert video.meta["tts_provider"] == "edge"
    assert video.meta["tts_voice"] == "nilar"
    assert video.meta["tts_rate"] == 1.2
    assert video.meta["tts_pitch"] == -5


def test_narration_text_falls_back_when_summary_failed():
    """Empty summary (provider/model failure) must NOT silently skip TTS:
    fall back to key points, then to the transcript itself."""
    import backend.celery_app.tasks as tasks

    assert tasks._narration_text(
        {"summary_short": "Real summary."}, []) == "Real summary."
    assert tasks._narration_text(
        {"summary_short": "", "description": "",
         "key_points": ["Point one.", "Point two."]}, []) == "Point one. Point two."
    assert tasks._narration_text(
        {"summary_short": "", "description": "", "key_points": []},
        [{"text": "hello world"}, {"text": "second line"}]) == "hello world second line"
    assert tasks._narration_text(
        {"summary_short": "", "description": "", "key_points": []}, []) == ""


def test_gemini_tts_uses_settings_model(tmp_path, monkeypatch):
    import asyncio
    import base64

    import httpx

    import backend.agents.agent_tts as tts_mod

    seen: list[str] = []

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"data": base64.b64encode(b"\x00\x00").decode()}}]}}]}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, params=None, json=None):
            seen.append(url)
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    settings = SimpleNamespace(gemini_keys=["k"],
                               GEMINI_TTS_MODEL="gemini-9-custom-tts")
    asyncio.run(tts_mod._synthesize_gemini("Hi", "Kore", settings, tmp_path / "x.wav"))
    assert "gemini-9-custom-tts" in seen[0]


def test_intro_outro_text_resolution():
    import backend.celery_app.tasks as tasks

    summary = {"title": "Recap Title"}
    # Custom text wins.
    assert tasks._intro_outro_texts(
        {"intro_enabled": True, "intro_text": "My Intro",
         "outro_enabled": True, "outro_text": "My Outro"}, summary) == (
        "My Intro", "My Outro")
    # Empty custom text -> defaults.
    assert tasks._intro_outro_texts(
        {"intro_enabled": True, "intro_text": "",
         "outro_enabled": True, "outro_text": "  "}, summary) == (
        "Recap Title", "Thanks for watching — AI Video Recap")
    # Disabled -> None (card dropped).
    assert tasks._intro_outro_texts(
        {"intro_enabled": False, "outro_enabled": False}, summary) == (None, None)
    # Missing keys -> backward compat (enabled, defaults).
    assert tasks._intro_outro_texts({}, summary) == (
        "Recap Title", "Thanks for watching — AI Video Recap")


def test_persist_ingestion_stores_intro_outro_text():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.agents.agent01_ingestion import IngestionResult, persist_ingestion
    from backend.database import Base, Video

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(__import__("backend.database", fromlist=["User"]).User(
        id="u1", email="u1@dev.local"))
    db.commit()
    res = IngestionResult(
        ok=True, job_id="j1", video_id="v1", container="mp4",
        metadata={"original_name": "a.mp4", "duration_sec": 10.0,
                  "size_bytes": 100, "sha256_prefix": "ab"})
    persist_ingestion(db, res, user_id="u1",
                      storage_path="uploads/v1/original.mp4",
                      intro_text="Hello Intro", outro_text="Bye Outro")
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["intro_text"] == "Hello Intro"
    assert video.meta["outro_text"] == "Bye Outro"
