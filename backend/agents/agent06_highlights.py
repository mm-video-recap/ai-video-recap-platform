"""
Agent 06 — Highlights Agent.

Scores candidate moments from three signals and merges them into the final
highlight reel list:
  * transcript density  — segments with lots of speech / exclamations
  * scene changes       — cuts from agent02 mark visual novelty
  * visual events       — vision agent's "events" notes (people, action)

Each highlight: {start, end, score} with score in 0..1, sorted by score desc.
Deterministic and dependency-free (no LLM needed) so highlights always work
even when every AI provider is down. Never raises.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("agents.highlights")

_EXCITED = re.compile(r"[!?？！]|wow|amazing|incredible|breaking|shocking|finally",
                      re.IGNORECASE)


class HighlightsAgent:
    def __init__(self, top_n: int = 8, min_clip_sec: float = 5.0,
                 max_clip_sec: float = 45.0,
                 max_total_sec: float | None = None):
        self.top_n = top_n
        self.min_clip_sec = min_clip_sec
        self.max_clip_sec = max_clip_sec
        # Cap on the TOTAL recap duration (recap style): keep the
        # highest-scoring clips whose combined duration fits, always
        # keeping at least the top clip.
        self.max_total_sec = max_total_sec

    def select(self, transcript: list[dict], segments: list[dict],
               vision: dict, job_id: str,
               duration_sec: float | None = None) -> dict:
        try:
            cands = self._candidates(transcript, segments, vision, duration_sec)
            scored = sorted((self._score(c, transcript) for c in cands),
                            key=lambda h: h["score"], reverse=True)
            highlights = scored[:self.top_n]
            if self.max_total_sec:
                kept: list[dict] = []
                total = 0.0
                for h in highlights:
                    dur = max(0.0, float(h.get("end", 0)) - float(h.get("start", 0)))
                    if kept and total + dur > self.max_total_sec:
                        continue
                    kept.append(h)
                    total += dur
                highlights = kept
            log.info("highlights job=%s: %d selected from %d candidates",
                     job_id, len(highlights), len(cands))
            return {"highlights": highlights, "degraded": False}
        except Exception as exc:  # never crash the worker
            log.exception("highlights job=%s failed", job_id)
            return {"highlights": [], "degraded": True, "error": str(exc)[:300]}

    # -- internals -----------------------------------------------------------
    def _candidates(self, transcript, segments, vision, duration_sec):
        cands: list[dict] = []
        # Candidate windows anchored on transcript segments (merged to min length)
        buf: list[dict] = []
        for seg in transcript or []:
            buf.append(seg)
            span = (seg.get("end", 0) or 0) - (buf[0].get("start", 0) or 0)
            if span >= self.min_clip_sec:
                cands.append({"start": buf[0].get("start", 0),
                              "end": seg.get("end", 0), "kind": "speech"})
                buf = []
        if buf:
            cands.append({"start": buf[0].get("start", 0),
                          "end": buf[-1].get("end", 0), "kind": "speech"})
        # Scene-change windows
        for s in segments or []:
            start, end = s.get("start", 0), s.get("end", 0)
            if end - start >= self.min_clip_sec:
                cands.append({"start": start,
                              "end": min(end, start + self.max_clip_sec),
                              "kind": "scene"})
        # Vision event windows (centered on the frame's estimated timestamp)
        frames = (vision or {}).get("frames", [])
        for f in frames:
            if f.get("events"):
                idx = f.get("index", 0) or 0
                est = (idx + 0.5) * (self.max_clip_sec / 2)
                cands.append({"start": max(0.0, est - 10),
                              "end": est + 10, "kind": "visual"})
        # Clamp + drop empties, merge heavy overlaps
        clean = []
        for c in cands:
            start, end = float(c["start"]), float(c["end"])
            if duration_sec:
                start, end = max(0.0, start), min(duration_sec, end)
            if end - start >= self.min_clip_sec:
                clean.append({"start": round(start, 1), "end": round(end, 1),
                              "kind": c["kind"]})
        return self._dedupe(clean)

    def _dedupe(self, cands: list[dict]) -> list[dict]:
        cands.sort(key=lambda c: c["start"])
        merged: list[dict] = []
        for c in cands:
            if merged and c["start"] < merged[-1]["end"] - 1.0:
                # overlapping: keep the longer one
                if c["end"] - c["start"] > merged[-1]["end"] - merged[-1]["start"]:
                    merged[-1] = c
            else:
                merged.append(c)
        return merged

    def _score(self, cand: dict, transcript: list[dict]) -> dict:
        start, end = cand["start"], cand["end"]
        words, excited = 0, 0
        for seg in transcript or []:
            s, e = seg.get("start", 0) or 0, seg.get("end", 0) or 0
            if e >= start and s <= end:
                text = seg.get("text", "")
                words += len(text.split())
                if _EXCITED.search(text):
                    excited += 1
        density = min(1.0, words / 60.0)
        kind_bonus = {"speech": 0.25, "scene": 0.15, "visual": 0.30}[cand["kind"]]
        length_penalty = max(0.0, (end - start - 30) / 60.0) * 0.2
        score = max(0.0, min(1.0, 0.2 + density * 0.4 + excited * 0.1
                             + kind_bonus - length_penalty))
        return {"start": start, "end": round(end, 1),
                "score": round(score, 3), "kind": cand["kind"]}
