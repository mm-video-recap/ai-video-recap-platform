"""
Agent 04 — Vision Analysis Agent.

Samples frames (default: up to 12 evenly spread) and asks the provider
manager's vision chain (HF -> Gemini -> OpenRouter) to describe each frame:
objects / people / environment / notable events.

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
from pathlib import Path

import httpx

log = logging.getLogger("agents.vision")

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
        frames: list[dict] = []
        degraded = False
        try:
            if not frame_files:
                return {"frames": [], "degraded": True,
                        "error": "no frames available"}
            # Even spread across the video
            n = len(frame_files)
            step = max(1, n // max_frames)
            picks = frame_files[::step][:max_frames]
            log.info("vision job=%s: analyzing %d frames", job_id, len(picks))

            for idx, f in enumerate(picks):
                entry: dict = {"file": f, "index": idx}
                try:
                    desc = self._ollama_describe(Path(f))
                    engine = "ollama"
                    if desc is None and self.provider_manager is not None:
                        desc, engine = asyncio.run(
                            self.provider_manager.describe_frame(f, VISION_PROMPT))
                        desc = desc if isinstance(desc, dict) else {"description": str(desc)}
                    if desc is None:
                        raise RuntimeError("no vision backend available")
                    entry.update(_normalize(desc))
                    entry["engine"] = engine
                except Exception as exc:
                    log.warning("vision job=%s frame %d failed: %s", job_id, idx, exc)
                    entry["error"] = str(exc)[:200]
                    degraded = True
                frames.append(entry)
        except Exception as exc:  # never crash the worker
            log.exception("vision job=%s failed", job_id)
            return {"frames": frames, "degraded": True, "error": str(exc)[:500]}
        return {"frames": frames, "degraded": degraded or not frames}


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
