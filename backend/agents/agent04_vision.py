"""
Agent 04 — Vision Analysis Agent.

Samples frames (default: up to 12 evenly spread) and asks the provider
manager's vision chain (HF -> Gemini -> OpenRouter) to describe each frame:
objects / people / environment / notable events.

Speed (2026-10-17): frames used to be analyzed ONE BY ONE, each a
separate cloud call — 8 frames took ~5 min live. Now frames are analyzed
in PARALLEL with a bounded semaphore (default 3 concurrent, see
VISION_CONCURRENCY), and each frame is downscaled to <=768px on its long
side with ffmpeg before upload (smaller payload, faster transfer, and the
vision model needs no more detail than that for scene description).
A single frame failing never stops the others.

Optional local Ollama stub: if OLLAMA_URL is set, vision-capable ollama
models (e.g. llava) are tried FIRST, before the cloud chain. If Ollama is
unreachable the agent falls back to the cloud chain automatically.

Output: {"frames": [{file, timestamp, description, objects, people,
                     environment, events}], "degraded": bool}
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

log = logging.getLogger("agents.vision")

# Concurrent frame-analysis calls. 2-3 is the safe starting point on a
# free-tier Gemini quota (research: Gemini docs + community practice);
# raise via env only if the quota allows it.
VISION_CONCURRENCY = max(1, min(8, int(os.environ.get("VISION_CONCURRENCY", "3"))))
# Long side of the frame sent to the vision model. 768px keeps scene
# detail while cutting upload bytes ~60% vs the 1280px normalized frame.
VISION_MAX_SIDE = 768

VISION_PROMPT = """Analyze this video frame. Reply in compact JSON with keys:
{"objects": [...], "people": "description or 'none'", "environment": "...",
 "events": "...", "caption": "one-sentence summary"}"""


class VisionAgent:
    def __init__(self, provider_manager=None, ollama_url: str | None = None,
                 ollama_model: str = "llava"):
        self.provider_manager = provider_manager
        self.ollama_url = ollama_url or os.environ.get("OLLAMA_URL", "")
        self.ollama_model = ollama_model

    # -- optional local Ollama stub -----------------------------------------
    def _ollama_describe(self, image_path: Path) -> dict | None:
        if not self.ollama_url:
            return None
        try:
            raw = base64.b64encode(image_path.read_bytes()).decode()
            resp = httpx.post(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                json={"model": self.ollama_model, "prompt": VISION_PROMPT,
                      "images": [raw], "stream": False, "format": "json"},
                timeout=180,
            )
            if resp.status_code != 200:
                return None
            text = resp.json().get("response", "")
            return _parse_frame_json(text)
        except Exception as exc:
            log.warning("ollama vision failed (%s); falling back to cloud", exc)
            return None

    # -- main ----------------------------------------------------------------
    def analyze(self, frame_files: list[str], job_id: str,
                max_frames: int = 12) -> dict:
        try:
            if not frame_files:
                return {"frames": [], "degraded": True,
                        "error": "no frames available"}
            # Even spread across the video
            n = len(frame_files)
            step = max(1, n // max_frames)
            picks = frame_files[::step][:max_frames]
            log.info("vision job=%s: analyzing %d frames (parallel x%d, max side %dpx)",
                     job_id, len(picks), VISION_CONCURRENCY, VISION_MAX_SIDE)
            with tempfile.TemporaryDirectory(prefix="vision-downscale-") as td:
                frames = asyncio.run(
                    self._analyze_all(picks, job_id, Path(td)))
        except Exception as exc:  # never crash the worker
            log.exception("vision job=%s failed", job_id)
            return {"frames": [], "degraded": True, "error": str(exc)[:500]}
        return {"frames": frames,
                "degraded": any("error" in f for f in frames) or not frames}

    async def _analyze_all(self, picks: list[str], job_id: str,
                           workdir: Path) -> list[dict]:
        sem = asyncio.Semaphore(VISION_CONCURRENCY)
        # gather preserves input order, so frames stay in timeline order.
        return list(await asyncio.gather(*[
            self._analyze_one(sem, idx, f, job_id, workdir)
            for idx, f in enumerate(picks)
        ]))

    async def _analyze_one(self, sem: asyncio.Semaphore, idx: int, f: str,
                           job_id: str, workdir: Path) -> dict:
        entry: dict = {"file": f, "index": idx}
        try:
            async with sem:
                # Downscale before upload: smaller payload, faster call.
                small = await asyncio.to_thread(_downscale_frame, Path(f), workdir)
                desc = await asyncio.to_thread(self._ollama_describe, small)
                engine = "ollama"
                if desc is None and self.provider_manager is not None:
                    desc, engine = await self.provider_manager.describe_frame(
                        str(small), VISION_PROMPT)
                    desc = desc if isinstance(desc, dict) else {"description": str(desc)}
                if desc is None:
                    raise RuntimeError("no vision backend available")
                entry.update(_normalize(desc))
                entry["engine"] = engine
        except Exception as exc:
            # One frame failing must never stop the others.
            log.warning("vision job=%s frame %d failed: %s", job_id, idx, exc)
            entry["error"] = str(exc)[:200]
        return entry


def _downscale_frame(src: Path, workdir: Path,
                     max_side: int = VISION_MAX_SIDE) -> Path:
    """Downscale a frame to fit within max_side x max_side (aspect kept).

    Returns the downscaled path, or the ORIGINAL path when ffmpeg is
    missing/fails — downscaling must never break vision.
    """
    try:
        out = workdir / f"{src.stem}-small.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-vf", f"scale={max_side}:{max_side}:force_original_aspect_ratio=decrease",
             "-q:v", "4", str(out)],
            timeout=60, capture_output=True)
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return out
        log.warning("vision downscale failed for %s, using original", src.name)
        return src
    except Exception as exc:
        log.warning("vision downscale failed for %s (%s), using original", src.name, exc)
        return src


def _parse_frame_json(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"description": text}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"description": text.strip()[:2000]}


def _normalize(desc: dict) -> dict:
    if "description" in desc and len(desc) == 1:
        parsed = _parse_frame_json(str(desc["description"]))
        if isinstance(parsed, dict) and "objects" in parsed:
            desc = parsed
    return {
        "objects": desc.get("objects", []),
        "people": desc.get("people", ""),
        "environment": desc.get("environment", ""),
        "events": desc.get("events", ""),
        "caption": desc.get("caption", "") or desc.get("description", ""),
    }
