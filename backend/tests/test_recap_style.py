"""Recap styles: short / detailed / cinematic / custom.

Style flows: upload query params -> video.meta -> ai_analyze
(_recap_style_config) -> HighlightsAgent (top_n + max_total_sec) and
SummaryAgent (tone/length prompt block). The legacy recap_style DB
column stays unused.
"""
import pytest


def test_style_config_mapping():
    from backend.celery_app.tasks import _recap_style_config

    short = _recap_style_config({"recap_style": "short"})
    assert (short["top_n"], short["max_total_sec"]) == (4, 60)

    detailed = _recap_style_config({"recap_style": "detailed"})
    assert (detailed["top_n"], detailed["max_total_sec"]) == (10, 300)

    cinematic = _recap_style_config({"recap_style": "cinematic"})
    assert (cinematic["top_n"], cinematic["max_total_sec"]) == (8, 180)

    custom = _recap_style_config({"recap_style": "custom",
                                  "recap_length_sec": 45,
                                  "recap_tone": "ဟာသဆန်ဆန် ပြောပြပါ"})
    assert custom["max_total_sec"] == 45
    assert custom["top_n"] == 3  # 45 // 15
    assert custom["tone"] == "ဟာသဆန်ဆန် ပြောပြပါ"

    # Unknown style -> detailed; custom length clamped to 15..900.
    assert _recap_style_config({"recap_style": "bogus"})["name"] == "detailed"
    assert _recap_style_config({})["name"] == "detailed"
    assert _recap_style_config({"recap_style": "custom",
                                "recap_length_sec": 5})["max_total_sec"] == 15
    assert _recap_style_config({"recap_style": "custom",
                                "recap_length_sec": 5000})["max_total_sec"] == 900


def test_highlights_max_total_sec_trims_lowest_scoring():
    """Total recap duration is capped; the top clip always survives."""
    from backend.agents.agent06_highlights import HighlightsAgent

    # 6 transcript segments of 10s each -> candidates of >=10s windows.
    transcript = [{"start": i * 10.0, "end": i * 10.0 + 9.0,
                   "text": f"line {i} with some words here"}
                  for i in range(6)]
    out = HighlightsAgent(top_n=6, max_total_sec=25).select(
        transcript, [], {}, "j1", duration_sec=60.0)
    highlights = out["highlights"]
    assert highlights, "at least the top clip must survive"
    total = sum(h["end"] - h["start"] for h in highlights)
    assert total <= 25.0


def test_highlights_no_cap_keeps_old_behavior():
    from backend.agents.agent06_highlights import HighlightsAgent

    transcript = [{"start": i * 10.0, "end": i * 10.0 + 9.0,
                   "text": f"line {i} with some words here"}
                  for i in range(6)]
    out = HighlightsAgent(top_n=6).select(
        transcript, [], {}, "j1", duration_sec=60.0)
    assert len(out["highlights"]) == 6


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
                           style={"name": "custom", "target_sec": 45,
                                  "tone": "ဟာသဆန်ဆန် ပြောပြပါ"})
    assert "CUSTOM" in custom
    assert "ဟာသဆန်ဆန် ပြောပြပါ" in custom
    assert "45" in custom

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
                "/api/videos/upload?recap_style=custom&recap_length_sec=45"
                "&recap_tone=funny",
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
        recap_style="custom", recap_length_sec=45, recap_tone="ဟာသဆန်")
    assert video.meta["recap_style"] == "custom"
    assert video.meta["recap_length_sec"] == 45
    assert video.meta["recap_tone"] == "ဟာသဆန်"
    # Defaults + invalid values are sanitized.
    class _Result2(_Result):
        video_id = "v2"
        job_id = "j2"

    video2, _ = persist_ingestion(
        db, _Result2(), user_id="u1", storage_path="uploads/v2/original.mp4",
        recap_style="bogus", recap_length_sec=5)
    assert video2.meta["recap_style"] == "detailed"
    assert video2.meta["recap_length_sec"] == 15
