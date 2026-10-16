"""Vision speedup: parallel frame analysis + downscale + chain robustness."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.agents.agent04_vision import VisionAgent, _downscale_frame
from backend.ai_provider.manager import ProviderError, ProviderManager


class FakeManager:
    """Fake provider manager tracking concurrency of describe_frame."""

    def __init__(self, fail_at: set[int] | None = None, delay: float = 0.05):
        self.fail_at = fail_at or set()
        self.delay = delay
        self.current = 0
        self.max_seen = 0
        self.lock = asyncio.Lock()

    async def describe_frame(self, image_path, prompt):
        async with self.lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
        try:
            await asyncio.sleep(self.delay)
            idx = int(Path(image_path).stem.split("-")[0].replace("frame", ""))
            if idx in self.fail_at:
                raise ProviderError("fake vision failure")
            return {"caption": f"frame {idx}", "objects": []}, "fake"
        finally:
            async with self.lock:
                self.current -= 1


def _frame_paths(n: int, tmp: Path) -> list[str]:
    paths = []
    for i in range(n):
        p = tmp / f"frame{i}.jpg"
        p.write_bytes(b"not-a-real-jpeg")
        paths.append(str(p))
    return paths


def test_parallel_all_succeed_order_preserved(tmp_path):
    mgr = FakeManager()
    out = VisionAgent(provider_manager=mgr).analyze(_frame_paths(6, tmp_path), "j1")
    assert len(out["frames"]) == 6
    assert out["degraded"] is False
    assert [f["index"] for f in out["frames"]] == list(range(6))
    assert [f["caption"] for f in out["frames"]] == [f"frame {i}" for i in range(6)]
    # Parallelism actually happened (sequential would peak at 1).
    assert mgr.max_seen >= 2


def test_one_frame_fails_others_succeed(tmp_path):
    mgr = FakeManager(fail_at={2})
    out = VisionAgent(provider_manager=mgr).analyze(_frame_paths(5, tmp_path), "j2")
    assert out["degraded"] is True
    assert "error" in out["frames"][2]
    assert out["frames"][0]["caption"] == "frame 0"
    assert out["frames"][4]["caption"] == "frame 4"


def test_downscale_reduces_large_frame(tmp_path):
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not available")
    src = tmp_path / "big.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720", "-frames:v", "1", str(src)],
                   check=True, timeout=30)
    small = _downscale_frame(src, tmp_path)
    assert small.exists() and small != src
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height",
                            "-of", "json", str(small)],
                           capture_output=True, text=True, check=True, timeout=30)
    dims = json.loads(probe.stdout)["streams"][0]
    assert max(dims["width"], dims["height"]) <= 768


def test_downscale_falls_back_to_original_on_failure(tmp_path):
    missing = tmp_path / "nope.jpg"
    assert _downscale_frame(missing, tmp_path) == missing


class _RawBoom:
    async def analyze_image(self, image_path, prompt):
        raise RuntimeError("raw SDK boom")  # NOT a ProviderError


class _Good:
    async def analyze_image(self, image_path, prompt):
        return {"caption": "ok"}


@pytest.mark.asyncio
async def test_describe_frame_continues_after_raw_exception():
    mgr = ProviderManager.__new__(ProviderManager)
    mgr.providers = {"huggingface": _RawBoom(), "gemini": _Good(),
                     "openrouter": _RawBoom()}
    mgr._log_usage = lambda *a, **k: None
    result, engine = await mgr.describe_frame("x.jpg", "prompt")
    assert result == {"caption": "ok"}
    assert engine == "gemini"
