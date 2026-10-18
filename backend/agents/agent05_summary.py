"""
Agent 05 — Summary Agent.

Builds the recap text products from the transcript + vision notes:
title, description, short summary, detailed summary, key points, timeline.

Output language selectable: "en" (default) or "my" (Myanmar/Burmese).
The LLM is asked for strict JSON; the agent validates and repairs the shape.
Never raises — returns a degraded skeleton on failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

log = logging.getLogger("agents.summary")

_SUMMARY_SCHEMA = """{
  "title": "short catchy title",
  "description": "1-2 sentence video description",
  "summary_short": "2-3 sentence recap",
  "summary_long": "detailed multi-paragraph recap",
  "key_points": ["point 1", "point 2", "..."],
  "timeline": [{"start": 0.0, "end": 12.5, "label": "Intro"}]
}"""


class SummaryAgent:
    def __init__(self, provider_manager):
        self.provider_manager = provider_manager

    def _prompt(self, transcript_text: str, vision_notes: str, lang: str,
                style: dict | None = None) -> str:
        lang_name = "Burmese (Myanmar language)" if lang == "my" else "English"
        style = style or {}
        style_name = style.get("name", "detailed")
        tone = style.get("tone", "")
        style_block = {
            "short": ("STYLE: SHORT recap. Be punchy and fast-paced: key "
                      "events only, no fluff. summary_short: 2-3 sentences. "
                      "summary_long: 1 short paragraph."),
            "detailed": ("STYLE: DETAILED recap. Be thorough: explain the "
                         "story and events in detail, in order. "
                         "summary_short: 1 paragraph. summary_long: 4-6 "
                         "paragraphs."),
            "cinematic": ("STYLE: CINEMATIC recap. Write like a movie "
                          "trailer narrator: dramatic pacing, vivid and "
                          "gripping language, a hook in the first line. "
                          "summary_short: 2-3 sentences with punch. "
                          "summary_long: 3-4 dramatic paragraphs."),
            "custom": ("STYLE: CUSTOM recap. "
                       + (f"User-requested tone: {tone}. " if tone else "")
                       + "Let the script be as long or short as the story needs."),
        }.get(style_name, "")
        return f"""You are an expert video recap writer. Write the recap in {lang_name}.

{style_block}

TRANSCRIPT (with timestamps in seconds):
{transcript_text[:12000]}

VISUAL NOTES (what is seen in the video):
{vision_notes[:6000]}

Produce a recap as strict JSON matching this schema (numbers for start/end are seconds):
{_SUMMARY_SCHEMA}

Rules:
- LANGUAGE IS MANDATORY: every text value in the JSON — title, description, summary_short, summary_long, each key_points entry, each timeline label — MUST be written in {lang_name}. Do not write any of them in English unless {lang_name} itself is English.
- timeline must cover the video in order, labels short, timestamps within the video length.
- key_points: 5-10 concrete points actually present in the content.
- Reply with ONLY the JSON object, no markdown fences."""

    def summarize(self, transcript: list[dict], vision: dict, job_id: str,
                  duration_sec: float | None = None, lang: str = "en",
                  style: dict | None = None) -> dict:
        lang = "my" if lang == "my" else "en"
        try:
            lines = [f"[{s.get('start', 0):.0f}-{s.get('end', 0):.0f}s] {s.get('text', '')}"
                     for s in (transcript or [])]
            transcript_text = "\n".join(lines) or "(no speech detected)"
            vision_notes = "\n".join(
                f"- {f.get('caption', '')} ({f.get('environment', '')})"
                for f in (vision or {}).get("frames", [])) or "(no visual analysis)"

            text, provider = asyncio.run(self.provider_manager.complete(
                "summary", self._prompt(transcript_text, vision_notes, lang,
                                        style=style),
                json_mode=True, max_tokens=3000))
            data = _extract_json(text)
            out = _validate(data, duration_sec)
            out["engine"] = provider
            out["degraded"] = False
            log.info("summary job=%s ok via %s", job_id, provider)
            return out
        except Exception as exc:
            log.exception("summary job=%s failed", job_id)
            return _skeleton(lang, error=str(exc)[:500])


def _extract_json(text: str) -> dict:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        return json.loads(m.group(0))
    raise ValueError("LLM did not return JSON")


def _validate(data: dict, duration_sec: float | None) -> dict:
    timeline = []
    for item in data.get("timeline", []) or []:
        try:
            start = max(0.0, float(item.get("start", 0)))
            end = float(item.get("end", start))
            if end <= start:
                continue
            if duration_sec and start >= duration_sec:
                continue
            if duration_sec:
                end = min(end, duration_sec)
            timeline.append({"start": round(start, 1), "end": round(end, 1),
                             "label": str(item.get("label", ""))[:160]})
        except (TypeError, ValueError):
            continue
    timeline.sort(key=lambda t: t["start"])
    return {
        "title": str(data.get("title", "Untitled Recap"))[:200],
        "description": str(data.get("description", ""))[:2000],
        "summary_short": str(data.get("summary_short", ""))[:4000],
        "summary_long": str(data.get("summary_long", ""))[:20000],
        "key_points": [str(p)[:400] for p in (data.get("key_points") or [])][:12],
        "timeline": timeline,
    }


def _skeleton(lang: str, error: str | None = None) -> dict:
    title = "ဗီဒီယို အကျဉ်းချုပ်" if lang == "my" else "Video Recap"
    out = {
        "title": title,
        "description": "",
        "summary_short": "",
        "summary_long": "",
        "key_points": [],
        "timeline": [],
        "engine": "none",
        "degraded": True,
    }
    if error:
        out["error"] = error
    return out
