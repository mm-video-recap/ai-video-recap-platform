"""Tests: Myanmar subtitles burn-in — bundled Padauk font + force_style."""
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.agents.agent07_rendering import RenderingAgent

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE),
                                  reason="ffmpeg/ffprobe not installed")


def test_bundled_padauk_font_exists():
    """The repo must ship a Myanmar font: the Railway image installs
    NO fonts, and DejaVu/Liberation have no Myanmar glyphs."""
    font = (Path(__file__).resolve().parent.parent
            / "assets" / "fonts" / "Padauk-Regular.ttf")
    assert font.exists()
    assert font.stat().st_size > 100_000


def test_find_font_prefers_bundled_padauk(tmp_path):
    agent = RenderingAgent(tmp_path)
    font = agent._find_font()
    assert font is not None
    assert font.name == "Padauk-Regular.ttf"


def test_font_family_mapping():
    assert RenderingAgent._font_family(Path("/x/Padauk-Regular.ttf")) == "Padauk"
    assert RenderingAgent._font_family(
        Path("/x/NotoSansMyanmar-Regular.ttf")) == "Noto Sans Myanmar"
    assert RenderingAgent._font_family(Path("/x/DejaVuSans.ttf")) == "DejaVu Sans"
    assert RenderingAgent._font_family(Path("/x/Unknown.ttf")) is None


def test_subtitle_vf_pins_myanmar_font(tmp_path):
    agent = RenderingAgent(tmp_path)
    vf = agent._subtitle_vf(Path("/tmp/s.srt"), Path("/fonts/Padauk-Regular.ttf"))
    assert "fontsdir=/fonts" in vf
    assert "Fontname=Padauk" in vf
    assert "Fontsize=24" in vf
    assert "PrimaryColour=" in vf


def test_subtitle_vf_without_known_font_has_no_force_style(tmp_path):
    agent = RenderingAgent(tmp_path)
    vf = agent._subtitle_vf(Path("/tmp/s.srt"), Path("/fonts/Unknown.ttf"))
    assert "force_style" not in vf


def _make_source(path: Path, dur: int = 4):
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i",
           f"color=c=0x1a2b4a:s=640x360:d={dur}:r=30",
           "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, capture_output=True, check=True, timeout=120)


@needs_ffmpeg
def test_render_burns_myanmar_subtitles(tmp_path):
    """End-to-end: Myanmar transcript -> mode == burned_in and the
    SRT on disk holds the Myanmar text."""
    src = tmp_path / "src.mp4"
    _make_source(src, dur=4)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(
        src,
        [{"start": 0, "end": 4}],
        [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ"},
         {"start": 2, "end": 4, "text": "ပြောပြပေးပါမယ်"}],
        "Title", "job-myanmar-sub",
        intro_enabled=False, outro_enabled=False)
    assert res.ok, res.errors
    assert res.subtitle_mode == "burned_in"
    assert res.subtitle_path and Path(res.subtitle_path).exists()
    srt = Path(res.subtitle_path).read_text(encoding="utf-8")
    assert "မင်္ဂလာပါ" in srt
    assert "ပြောပြပေးပါမယ်" in srt
