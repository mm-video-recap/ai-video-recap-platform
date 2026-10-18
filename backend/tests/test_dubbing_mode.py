"""Full dubbing mode: the output IS the original video, re-voiced.

Upload output_mode="dubbing" keeps the full normalized video (no
highlight clips, no intro/outro), burns/muxes the translated FULL
transcript on the original timeline, and replaces the audio with TTS
narration of the full translated transcript. Recap mode is unchanged.
"""
import subprocess

import pytest


def _make_clip(path, color="0x1a2b4a", dur=4, with_audio=True):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"color=c={color}:s=640x360:d={dur}:r=30"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={dur}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True,
        timeout=30, check=True)
    return float((p.stdout or "0").strip())


def _has_audio(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30)
    return bool((p.stdout or "").strip())


def test_dubbing_keeps_full_video_and_ignores_intro(tmp_path):
    """Dubbing: output duration == source duration (no clip cutting,
    no 2s intro card), subtitles on the original timeline."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    transcript = [
        {"start": 0, "end": 2, "text": "မင်္ဂလာပါ ပြောပြပေးပါမယ်"},
        {"start": 2, "end": 4, "text": "ဒုတိယ စာကြောင်း ဖြစ်ပါတယ်"},
    ]
    res = agent.render(main, [{"start": 0, "end": 2}], transcript,
                       "Title", "j1", output_mode="dubbing",
                       intro_enabled=True, outro_enabled=True)
    assert res.ok, res.errors
    # Full 4s source, NOT 4s + 2s intro card + outro card.
    assert abs(_duration(res.video_path) - 4.0) < 0.6
    assert res.subtitle_mode in ("burned_in", "soft")
    # SRT keeps ORIGINAL timestamps (no remap): last cue ends at ~4s.
    srt = (tmp_path / "results" / "j1" / "subtitles.srt").read_text(
        encoding="utf-8")
    assert "00:00:03" in srt or "00:00:04" in srt


def test_dubbing_tts_replaces_audio(tmp_path, monkeypatch):
    """Dubbing + TTS: narration audio replaces the original track."""
    from backend.agents import agent_tts
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    # Fake narration wav (distinct tone) returned by the mocked synth.
    narr = tmp_path / "narr.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:d=3",
         str(narr)], capture_output=True, timeout=30, check=True)

    def fake_synth(*args, **kwargs):
        return str(narr)

    monkeypatch.setattr(agent_tts, "synthesize_narration", fake_synth)
    agent = RenderingAgent(tmp_path / "results")
    transcript = [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ"}]
    res = agent.render(main, [], transcript, "Title", "j1",
                       output_mode="dubbing", intro_enabled=False,
                       outro_enabled=False,
                       narration_text="မင်္ဂလာပါ ပြောပြပေးပါမယ်",
                       tts_provider="edge", tts_voice="thiha")
    assert res.ok, res.errors
    assert abs(_duration(res.video_path) - 4.0) < 0.6
    assert _has_audio(res.video_path)
    assert any("narration: edge/thiha" in w for w in res.warnings)


def test_recap_still_requires_highlights(tmp_path):
    """Recap mode is unchanged: no highlights -> render error."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [], [], "Title", "j1", output_mode="recap")
    assert not res.ok
    assert any("no highlights" in e for e in res.errors)


def test_upload_output_mode_validated(client, auth_headers, make_mp4_bytes,
                                      monkeypatch):
    """output_mode=dubbing is accepted; an unknown mode is rejected."""
    from unittest import mock

    from backend.config import get_settings

    monkeypatch.setenv("OWNER_EMAIL", "owner@dev.local")
    get_settings.cache_clear()
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    try:
        headers = auth_headers("owner@dev.local")
        files = {"file": ("clip.mp4", make_mp4_bytes(4096), "video/mp4")}
        with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                        return_value=fake_meta), \
            mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                       return_value=True):
            r = client.post("/api/videos/upload?output_mode=dubbing",
                            files=files, headers=headers)
            assert r.status_code == 201, r.text
            r = client.post("/api/videos/upload?output_mode=bogus",
                            files=files, headers=headers)
            assert r.status_code == 422
    finally:
        get_settings.cache_clear()


def test_persist_ingestion_stores_output_mode():
    """persist_ingestion writes output_mode into video.meta."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.agents.agent01_ingestion import persist_ingestion
    from backend.database import Base

    class _Result:
        ok = True
        video_id = "v1"
        job_id = "j1"
        container = "mp4"
        metadata = {"original_name": "a.mp4", "size_bytes": 10,
                    "duration_sec": 4, "width": 640, "height": 360,
                    "sha256_prefix": "abc", "user_id": "u1"}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    video, _job = persist_ingestion(
        db, _Result(), user_id="u1", storage_path="uploads/v1/original.mp4",
        output_mode="dubbing")
    assert video.meta["output_mode"] == "dubbing"
