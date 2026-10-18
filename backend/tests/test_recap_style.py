"""Recap styles: short / detailed / cinematic / custom.

Style flows: upload query params -> video.meta -> ai_analyze
(_recap_style_config) -> HighlightsAgent (top_n + max_total_sec) and
SummaryAgent (tone/length prompt block). The legacy recap_style DB
column stays unused.
"""
import pytest


def test_style_config_mapping():
    from backend.celery_app.tasks import _recap_style_config

    # No minute caps anywhere (user 2026-10-18): the AI script decides
    # the length; the video follows the narration.
    short = _recap_style_config({"recap_style": "short"})
    assert short["top_n"] == 4
    assert short["tone"] == ""
    assert "max_total_sec" not in short

    detailed = _recap_style_config({"recap_style": "detailed"})
    assert detailed["top_n"] == 12

    cinematic = _recap_style_config({"recap_style": "cinematic"})
    assert cinematic["top_n"] == 8

    custom = _recap_style_config({"recap_style": "custom",
                                  "recap_tone": "ဟာသဆန်ဆန် ပြောပြပါ"})
    assert custom["top_n"] == 12
    assert custom["tone"] == "ဟာသဆန်ဆန် ပြောပြပါ"

    # Unknown style -> detailed.
    assert _recap_style_config({"recap_style": "bogus"})["name"] == "detailed"
    assert _recap_style_config({})["name"] == "detailed"


def _make_narr_wav(path, dur):
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=660:d={dur}",
         str(path)], capture_output=True, timeout=30, check=True)


def _make_clip(path, dur=4):
    import subprocess
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"color=c=0x1a2b4a:s=640x360:d={dur}:r=30",
           "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-shortest", str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _duration(path):
    import subprocess
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True,
        timeout=30, check=True)
    return float((p.stdout or "0").strip())


def _render_with_narration(tmp_path, monkeypatch, narr_dur):
    """Render a 4s recap with a mocked narration of narr_dur seconds."""
    from backend.agents import agent_tts
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    narr = tmp_path / "narr.wav"
    _make_narr_wav(narr, narr_dur)
    monkeypatch.setattr(agent_tts, "synthesize_narration",
                        lambda *a, **k: str(narr))
    agent = RenderingAgent(tmp_path / "results")
    transcript = [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ"},
                  {"start": 2, "end": 4, "text": "ပြောပြပေးပါမယ်"}]
    return agent.render(
        main, [{"start": 0, "end": 4}], transcript, "Title", "j1",
        output_mode="recap", intro_enabled=False, outro_enabled=False,
        narration_text="မင်္ဂလာပါ ပြောပြပေးပါမယ်", tts_provider="edge",
        tts_voice="thiha")


def test_recap_video_loops_clips_to_cover_narration(tmp_path, monkeypatch):
    """Narration is king: a 6s narration over a 4s highlight loops the
    clip so the video reaches ~6s (not 4s + silence, not sped-up audio)."""
    res = _render_with_narration(tmp_path, monkeypatch, narr_dur=6)
    assert res.ok, res.errors
    assert abs(_duration(res.video_path) - 6.0) < 0.8


def test_recap_video_trims_to_narration(tmp_path, monkeypatch):
    """A 2s narration over a 4s highlight trims the video to ~2s."""
    res = _render_with_narration(tmp_path, monkeypatch, narr_dur=2)
    assert res.ok, res.errors
    assert abs(_duration(res.video_path) - 2.0) < 0.8


def test_recap_without_narration_keeps_all_highlights(tmp_path):
    """No narration (original audio): old behavior, all highlights."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(main, [{"start": 0, "end": 4}], [], "Title", "j1",
                       output_mode="recap", intro_enabled=False,
                       outro_enabled=False)
    assert res.ok, res.errors
    assert abs(_duration(res.video_path) - 4.0) < 0.6


def test_summary_prompt_carries_style():
    from unittest import mock

    from backend.agents.agent05_summary import SummaryAgent

    agent = SummaryAgent(mock.MagicMock())
    cinematic = agent._prompt("t", "v", "my",
                             style={"name": "cinematic", "target_sec": 180,
                                    "tone": ""})
    assert "CINEMATIC" in cinematic
    assert "dramatic" in cinematic.lower()

    custom = agent._prompt("t", "v", "my",
                           style={"name": "custom",
                                  "tone": "ဟာသဆန်ဆန် ပြောပြပါ"})
    assert "CUSTOM" in custom
    assert "ဟာသဆန်ဆန် ပြောပြပါ" in custom
    # No minute numbers anywhere in the style blocks (user 2026-10-18).
    assert "60 seconds" not in custom and "300 seconds" not in custom

    short = agent._prompt("t", "v", "my", style={"name": "short"})
    assert "SHORT" in short


def test_upload_recap_style_validated(client, auth_headers, make_mp4_bytes,
                                      monkeypatch):
    """recap_style=cinematic accepted; bogus rejected; custom params flow."""
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
            r = client.post(
                "/api/videos/upload?recap_style=cinematic",
                files=files, headers=headers)
            assert r.status_code == 201, r.text
            r = client.post(
                "/api/videos/upload?recap_style=custom&recap_tone=funny",
                files=files, headers=headers)
            assert r.status_code == 201, r.text
            r = client.post("/api/videos/upload?recap_style=bogus",
                            files=files, headers=headers)
            assert r.status_code == 422
    finally:
        get_settings.cache_clear()


def test_persist_ingestion_stores_recap_style():
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
        recap_style="custom", recap_tone="ဟာသဆန်")
    assert video.meta["recap_style"] == "custom"
    assert video.meta["recap_tone"] == "ဟာသဆန်"
    assert "recap_length_sec" not in video.meta
    # Defaults + invalid values are sanitized.
    class _Result2(_Result):
        video_id = "v2"
        job_id = "j2"

    video2, _ = persist_ingestion(
        db, _Result2(), user_id="u1", storage_path="uploads/v2/original.mp4",
        recap_style="bogus")
    assert video2.meta["recap_style"] == "detailed"
    assert video2.meta["recap_tone"] == ""
