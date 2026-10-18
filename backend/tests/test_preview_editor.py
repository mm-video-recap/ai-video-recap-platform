"""Preview editor (user 2026-10-18): blur boxes + subtitle position/size.

The upload page's Preview canvas lets the user draw blur boxes (drag to
move, corner handle to resize) and drag the subtitle line up/down with
a size slider. The backend burns them into the final video exactly as
edited: blur via an FFmpeg boxblur/overlay filtergraph in the final
normalize pass, subtitles via libass force_style position + size.
"""
import json
import subprocess

import pytest


def _agent(tmp_path):
    from backend.agents.agent07_rendering import RenderingAgent
    return RenderingAgent(tmp_path / "results")


def test_blur_graph_builds_chained_overlays():
    from backend.agents.agent07_rendering import RenderingAgent
    import tempfile
    agent = RenderingAgent(tempfile.mkdtemp())

    graph, out = agent._blur_graph([
        {"x": 0.1, "y": 0.4, "w": 0.8, "h": 0.2, "intensity": 22},
        {"x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2, "intensity": 10},
    ])
    assert out == "v1"
    assert graph.count("boxblur") == 2
    assert "luma_radius=22" in graph
    assert "chroma_radius=12" in graph  # chroma pinned < 18
    assert "[0:v]crop=" in graph
    assert "overlay=x=" in graph
    # iw/ih only inside crop; overlay uses main_w/main_h
    assert "main_w" in graph and "main_h" in graph


def test_blur_graph_skips_invalid_and_empty():
    from backend.agents.agent07_rendering import RenderingAgent
    import tempfile
    agent = RenderingAgent(tempfile.mkdtemp())

    assert agent._blur_graph(None) == ("", "0:v")
    assert agent._blur_graph([]) == ("", "0:v")
    # out-of-frame box + junk entry are skipped, never fail
    graph, out = agent._blur_graph([
        {"x": 0.9, "y": 0.9, "w": 0.5, "h": 0.5, "intensity": 22},
        "junk",
        {"x": 0.1, "y": 0.1},  # missing w/h
    ])
    assert (graph, out) == ("", "0:v")
    # intensity clamped to 1..50
    graph, _ = agent._blur_graph(
        [{"x": 0, "y": 0, "w": 0.5, "h": 0.5, "intensity": 999}])
    assert "luma_radius=50" in graph


def test_subtitle_vf_position_and_size():
    from pathlib import Path
    from backend.agents.agent07_rendering import RenderingAgent
    import tempfile
    agent = RenderingAgent(tempfile.mkdtemp())
    agent._font_family = lambda p: "Padauk"

    # Fontsize/MarginV are ASS script units (PlayResY=288), NOT video
    # pixels: fractions are multiplied by 288 so the burn matches the
    # preview pill 1:1 (measured 2026-10-18).
    vf = agent._subtitle_vf(Path("/tmp/x.srt"), Path("/tmp/f.ttf"))
    assert "Fontsize=10" in vf and "Alignment=2" in vf  # 0.033*288
    # bottom position: MarginV = (1-y)*288
    vf = agent._subtitle_vf(Path("/tmp/x.srt"), Path("/tmp/f.ttf"),
                            sub_y_frac=0.9)
    assert "Alignment=2" in vf and "MarginV=29" in vf  # 0.1*288
    # top half: Alignment 8, MarginV from the top
    vf = agent._subtitle_vf(Path("/tmp/x.srt"), Path("/tmp/f.ttf"),
                            sub_y_frac=0.2)
    assert "Alignment=8" in vf and "MarginV=58" in vf  # 0.2*288
    # bigger text
    vf = agent._subtitle_vf(Path("/tmp/x.srt"), Path("/tmp/f.ttf"),
                            font_size_frac=0.06)
    assert "Fontsize=17" in vf  # 0.06*288


def _make_clip(path, dur=4):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"color=c=0x2a4a6a:s=640x360:d={dur}:r=30",
           "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-shortest", str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def test_render_with_blur_burns_region(tmp_path):
    """End-to-end: a blur box survives the full render (filter_complex
    path) and the output still plays at the right duration."""
    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    transcript = [
        {"start": 0, "end": 2, "text": "မင်္ဂလာပါ ပြောပြပေးပါမယ်"},
        {"start": 2, "end": 4, "text": "ဒုတိယ စာကြောင်း ဖြစ်ပါတယ်"},
    ]
    res = agent.render(
        main, [{"start": 0, "end": 4}], transcript, "Title", "jblur",
        output_mode="dubbing",
        blur_regions=[{"x": 0.1, "y": 0.4, "w": 0.8, "h": 0.2,
                       "intensity": 22}],
        subtitle_y=0.9, subtitle_size=0.05)
    assert res.ok, res.errors
    assert res.subtitle_mode == "burned_in"
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(res.video_path)],
        capture_output=True, text=True, timeout=30, check=True)
    assert abs(float((p.stdout or "0").strip()) - 4.0) < 0.6


def test_blur_applied_before_subtitle_burn(tmp_path, caplog):
    """Layer order (user 2026-10-18): the blur pass must run on `joined`
    BEFORE subtitles are burned — otherwise the blur would cover the
    subtitle text where they overlap (the preview canvas paints the
    subtitle pill above the blur boxes). Proven by the existence of
    the intermediate joined_blur.mp4, which only the pre-burn pass
    creates."""
    import logging

    from backend.agents.agent07_rendering import RenderingAgent

    main = tmp_path / "main.mp4"
    _make_clip(main, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    transcript = [
        {"start": 0, "end": 4, "text": "မင်္ဂလာပါ စမ်းသပ်နေပါတယ်"},
    ]
    with caplog.at_level(logging.INFO):
        res = agent.render(
            main, [{"start": 0, "end": 4}], transcript, "Title", "jorder",
            output_mode="dubbing",
            # box deliberately covers the subtitle line
            blur_regions=[{"x": 0.05, "y": 0.55, "w": 0.9, "h": 0.4,
                           "intensity": 22}],
            subtitle_y=0.75, subtitle_size=0.06)
    assert res.ok, res.errors
    assert res.subtitle_mode == "burned_in"
    # The pre-burn blur pass ran and produced its intermediate file…
    assert (tmp_path / "results" / "jorder" / "joined_blur.mp4").exists()
    assert "applied 1 blur region(s)" in caplog.text
    # …and the job did not fall back to "no blur" either.
    assert not any("without blur" in w for w in res.warnings)


def test_upload_blur_regions_validated(client, auth_headers, make_mp4_bytes,
                                       monkeypatch):
    """Valid blur JSON accepted; malformed / out-of-range rejected."""
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
        good = json.dumps([{"x": 0.1, "y": 0.4, "w": 0.8, "h": 0.2,
                             "intensity": 22}])
        with mock.patch("backend.agents.agent01_ingestion._ffprobe_metadata",
                        return_value=fake_meta), \
            mock.patch("backend.celery_app.tasks.enqueue_pipeline",
                       return_value=True):
            r = client.post(
                f"/api/videos/upload?blur_regions={good}"
                "&subtitle_y=0.85&subtitle_size=0.05",
                files=files, headers=headers)
            assert r.status_code == 201, r.text

            r = client.post("/api/videos/upload?blur_regions=notjson",
                            files=files, headers=headers)
            assert r.status_code == 400

            bad = json.dumps([{"x": 0.9, "y": 0.9, "w": 0.5, "h": 0.5}])
            r = client.post(f"/api/videos/upload?blur_regions={bad}",
                            files=files, headers=headers)
            assert r.status_code == 400

            bad_int = json.dumps([{"x": 0.1, "y": 0.1, "w": 0.2,
                                   "h": 0.2, "intensity": 99}])
            r = client.post(f"/api/videos/upload?blur_regions={bad_int}",
                            files=files, headers=headers)
            assert r.status_code == 400

            many = json.dumps([{"x": 0, "y": 0, "w": 0.1, "h": 0.1}] * 11)
            r = client.post(f"/api/videos/upload?blur_regions={many}",
                            files=files, headers=headers)
            assert r.status_code == 400
    finally:
        get_settings.cache_clear()


def test_persist_ingestion_stores_preview_overlays():
    """blur_regions + subtitle_y/size land in video.meta."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.agents.agent01_ingestion import persist_ingestion
    from backend.database import Base

    class _Result:
        ok = True
        video_id = "v1"
        job_id = "j1"
        container = "mp4"
        errors = []
        metadata = {}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        video, _job = persist_ingestion(
            db, _Result(), user_id="u1", storage_path="p",
            blur_regions=[{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4,
                           "intensity": 30}],
            subtitle_y=0.85, subtitle_size=0.05)
        assert video.meta["blur_regions"] == [
            {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "intensity": 30}]
        assert video.meta["subtitle_y"] == 0.85
        assert video.meta["subtitle_size"] == 0.05
    finally:
        db.close()
