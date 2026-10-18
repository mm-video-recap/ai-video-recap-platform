"""Tests: uploaded intro/outro VIDEOS replace the text title cards.

The final recap is intro video + recap clips + outro video, concatenated
at render time. A missing/unusable side video falls back to the text
card, never failing the job. The subtitle remap offset is the intro
part's real duration (2.0s for a text card, the video length for an
uploaded intro video).
"""
import subprocess
from unittest import mock

import pytest
from fastapi import HTTPException


def _make_clip(path, color, dur, with_audio=True, channels=1):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"color=c={color}:s=640x360:d={dur}:r=30"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={dur}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", str(channels), "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _audio_channels(path):
    import json

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True)
    streams = json.loads(out.stdout).get("streams", [])
    return streams[0]["channels"] if streams else None


def _decodes_clean(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                        "-f", "null", "-"],
                       capture_output=True, text=True, timeout=120)
    return p.returncode == 0


def _video_fps(path):
    import json

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True)
    streams = json.loads(out.stdout).get("streams", [])
    return streams[0]["r_frame_rate"] if streams else None


def _has_faststart(path):
    """True when the moov atom comes before mdat (moov at the front)."""
    import struct

    with open(path, "rb") as f:
        data = f.read()
    off = 0
    order = []
    while off + 8 <= len(data):
        size = struct.unpack(">I", data[off:off + 4])[0]
        typ = data[off + 4:off + 8].decode("latin1")
        if size == 1:
            size = struct.unpack(">Q", data[off + 8:off + 16])[0]
        elif size == 0:
            size = len(data) - off
        order.append(typ)
        if size <= 0:
            break
        off += size
    return ("moov" in order and "mdat" in order
            and order.index("moov") < order.index("mdat"))


def test_render_mono_side_videos_with_stereo_main_stays_stereo(tmp_path):
    """REGRESSION (live 2026-10-17): a MONO intro/outro + STEREO main
    clip produced a broken mixed-layout concat — the result showed
    0:00/black and would not play. Every part must be forced to
    stereo 44100 Hz AAC so the concat stays uniform."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    intro = tmp_path / "intro.mp4"
    outro = tmp_path / "outro.mp4"
    _make_clip(main, "0x1a2b4a", 4, channels=2)   # stereo phone-style main
    _make_clip(intro, "0xff0000", 1.5)             # mono side videos
    _make_clip(outro, "0x00ff00", 1.0)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [{"start": 0, "end": 4}], [], "Title", "j1",
                       intro_enabled=True, outro_enabled=True,
                       intro_clip=intro, outro_clip=outro)
    assert res.ok, res.errors
    assert _audio_channels(res.video_path) == 2
    assert _decodes_clean(res.video_path)
    assert _video_fps(res.video_path) == "30/1"
    assert _has_faststart(res.video_path)
    # Final normalize: uniform 30fps header + moov at the front.
    assert _video_fps(res.video_path) == "30/1"
    assert _has_faststart(res.video_path)


def test_render_mono_main_with_stereo_side_videos_stays_stereo(tmp_path):
    """Same rule in the other direction: a mono SOURCE video must not
    break the concat either (clip cut forces stereo)."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    intro = tmp_path / "intro.mp4"
    outro = tmp_path / "outro.mp4"
    _make_clip(main, "0x1a2b4a", 4, channels=1)   # mono source
    _make_clip(intro, "0xff0000", 1.5, channels=2)
    _make_clip(outro, "0x00ff00", 1.0, channels=2)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [{"start": 0, "end": 4}], [], "Title", "j1",
                       intro_enabled=True, outro_enabled=True,
                       intro_clip=intro, outro_clip=outro)
    assert res.ok, res.errors
    assert _audio_channels(res.video_path) == 2
    assert _decodes_clean(res.video_path)


def test_render_uses_intro_outro_video_clips(tmp_path):
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    intro = tmp_path / "intro.mp4"
    outro = tmp_path / "outro.mp4"
    _make_clip(main, "0x1a2b4a", 4)
    _make_clip(intro, "0xff0000", 1.5)
    _make_clip(outro, "0x00ff00", 1.0)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [{"start": 0, "end": 4}], [], "Title", "j1",
                       intro_enabled=True, outro_enabled=True,
                       intro_clip=intro, outro_clip=outro)
    assert res.ok, res.errors
    dur = agent._duration(res.video_path)
    # intro 1.5 + clips 4 + outro 1 = 6.5 (concat rounding tolerance).
    assert dur is not None and abs(dur - 6.5) < 0.4, dur


def test_render_intro_video_falls_back_to_text_card(tmp_path):
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, "0x1a2b4a", 4)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [{"start": 0, "end": 4}], [], "Title", "j1",
                       intro_enabled=True, outro_enabled=False,
                       intro_clip=tmp_path / "missing.mp4")
    assert res.ok, res.errors
    assert any("intro video file not found" in w for w in res.warnings)
    dur = agent._duration(res.video_path)
    # Fallback text card is exactly 2s + 4s clips.
    assert dur is not None and abs(dur - 6.0) < 0.4, dur


def test_remap_uses_intro_video_duration():
    from backend.agents.agent07_rendering import RenderingAgent

    agent = RenderingAgent("/tmp")
    out = agent._remap_transcript(
        [{"start": 5, "end": 7, "text": "hi"}],
        [{"start": 0, "end": 10}], 3.5)
    assert [(c["start"], c["end"]) for c in out] == [(8.5, 10.5)]


def test_persist_ingestion_stores_intro_outro_video_keys():
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
                      intro_video_key="uploads/v1/intro.mp4",
                      outro_video_key="uploads/v1/outro.mp4")
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["intro_video_key"] == "uploads/v1/intro.mp4"
    assert video.meta["outro_video_key"] == "uploads/v1/outro.mp4"


def test_upload_with_intro_outro_files(client, auth_headers, make_mp4_bytes):
    import uuid

    user = f"io_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {
        "file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4"),
        "intro_file": ("intro.mp4", make_mp4_bytes(4096), "video/mp4"),
        "outro_file": ("outro.mp4", make_mp4_bytes(4096), "video/mp4"),
    }
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
    from backend.database import Video, get_session_factory

    db = get_session_factory()()
    try:
        video = db.query(Video).filter_by(id=r.json()["video_id"]).one()
        assert video.meta["intro_video_key"] == \
            f"uploads/{video.id}/intro.mp4"
        assert video.meta["outro_video_key"] == \
            f"uploads/{video.id}/outro.mp4"
    finally:
        db.close()


def test_upload_ignores_side_videos_when_toggle_off(client, auth_headers,
                                                     make_mp4_bytes):
    import uuid

    user = f"io_{uuid.uuid4().hex[:8]}"
    headers = auth_headers(user)
    files = {
        "file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4"),
        "intro_file": ("intro.mp4", make_mp4_bytes(4096), "video/mp4"),
    }
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                    return_value=fake_meta), \
         mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                    return_value=True):
        r = client.post("/api/videos/upload?intro_enabled=false",
                        files=files, headers=headers,
                        data={"gemini_key": "test-gemini",
                              "groq_key": "test-groq"})
    assert r.status_code == 201, r.text
    from backend.database import Video, get_session_factory

    db = get_session_factory()()
    try:
        video = db.query(Video).filter_by(id=r.json()["video_id"]).one()
        assert "intro_video_key" not in video.meta
    finally:
        db.close()


def test_store_side_video_rejects_corrupt(tmp_path):
    from backend.api.routes_videos import _store_side_video

    class _Storage:
        def put(self, path, key):
            raise AssertionError("corrupt file must not be stored")

    class _FakeUpload:
        filename = "intro.mp4"

        def __init__(self, data):
            import io
            self.file = io.BytesIO(data)

    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(b"not a video at all")
    with pytest.raises(HTTPException) as exc:
        _store_side_video(_FakeUpload(b"not a video at all"), "v1",
                          "intro", _Storage(), 2 * 1024 * 1024 * 1024)
    assert exc.value.status_code == 400


def test_store_side_video_accepts_valid(tmp_path):
    from backend.api.routes_videos import _store_side_video

    clip = tmp_path / "intro.mp4"
    _make_clip(clip, "0xff0000", 1)
    seen = {}

    class _Storage:
        def put(self, path, key):
            seen["key"] = key
            return key

    class _FakeUpload:
        filename = "intro.mp4"

        def __init__(self, data):
            import io
            self.file = io.BytesIO(data)

    key = _store_side_video(_FakeUpload(clip.read_bytes()), "v1",
                            "intro", _Storage(), 2 * 1024 * 1024 * 1024)
    assert key == "uploads/v1/intro.mp4"
    assert seen["key"] == key


def test_burn_in_failure_falls_back_to_soft_with_warning(tmp_path, monkeypatch):
    """REGRESSION (live 2026-10-18, #13): burn-in failed SILENTLY and the
    job fell back to soft subtitles — the user then saw NO Myanmar
    subtitles in players that ignore the embedded mov_text track.
    Burn failure must log, retry once, and warn visibly on fallback."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, "0x1a2b4a", 4)
    agent = RenderingAgent(tmp_path / "results")
    real_run = RenderingAgent._run

    def failing_burn(self, cmd, timeout=900):
        if any(isinstance(a, str) and "subtitles=" in a for a in cmd):
            return subprocess.CompletedProcess(cmd, 1, "", "fake burn failure")
        return real_run(self, cmd, timeout=timeout)

    monkeypatch.setattr(RenderingAgent, "_run", failing_burn)
    transcript = [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ ပြောပြပေးပါမယ်"}]
    res = agent.render(main, [{"start": 0, "end": 4}], transcript,
                       "Title", "j1", intro_enabled=False, outro_enabled=False)
    assert res.ok, res.errors
    assert res.subtitle_mode == "soft"
    assert any("separate subtitle track" in w for w in res.warnings)


def test_burn_in_retry_succeeds_after_one_transient_failure(tmp_path, monkeypatch):
    """A single transient burn-in failure must be retried, not silently
    downgraded to soft subtitles."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, "0x1a2b4a", 4)
    agent = RenderingAgent(tmp_path / "results")
    real_run = RenderingAgent._run
    calls = {"burn": 0}

    def flaky_burn(self, cmd, timeout=900):
        if any(isinstance(a, str) and "subtitles=" in a for a in cmd):
            calls["burn"] += 1
            if calls["burn"] == 1:
                return subprocess.CompletedProcess(cmd, 1, "", "transient")
        return real_run(self, cmd, timeout=timeout)

    monkeypatch.setattr(RenderingAgent, "_run", flaky_burn)
    transcript = [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ ပြောပြပေးပါမယ်"}]
    res = agent.render(main, [{"start": 0, "end": 4}], transcript,
                       "Title", "j1", intro_enabled=False, outro_enabled=False)
    assert res.ok, res.errors
    assert res.subtitle_mode == "burned_in"
    assert calls["burn"] == 2
    assert not any("separate subtitle track" in w for w in res.warnings)
