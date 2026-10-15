"""
Agent 02 — Video Processing Agent.

Responsibilities:
- Normalize the uploaded video (faststart, sane codecs) into processing/
- Extract a 16 kHz mono WAV for speech-to-text
- Extract frames (1 fps cap) for the vision agent
- Scene detection via ffmpeg's select filter
- Thumbnails (3 spread across the duration)
- Segment list [{start, end, scene_change}]

Works without ffmpeg installed: returns a degraded result (ok=False with a
clear error) instead of crashing. Every step is wrapped so one failure does
not silently poison the rest — failures are collected in `errors`.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("agents.processing")


@dataclass
class ProcessingResult:
    ok: bool
    job_id: str
    normalized_path: str | None = None
    audio_path: str | None = None
    frames_dir: str | None = None
    frame_files: list[str] = field(default_factory=list)
    thumbnails: list[str] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    duration_sec: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ProcessingAgent:
    def __init__(self, processing_root: str | Path):
        self.root = Path(processing_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")

    # -- helpers ------------------------------------------------------------
    def _run(self, cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        log.debug("ffmpeg cmd: %s", " ".join(cmd[:6]) + " ...")
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)

    def _probe_duration(self, path: Path) -> float | None:
        if not self.ffprobe:
            return None
        try:
            proc = self._run([self.ffprobe, "-v", "error", "-show_entries",
                              "format=duration", "-of", "json", str(path)], timeout=30)
            return float(json.loads(proc.stdout or "{}").get("format", {}).get("duration", 0) or 0) or None
        except Exception:
            return None

    # -- main ---------------------------------------------------------------
    def process(self, video_path: str | Path, job_id: str,
                max_frames: int = 120) -> ProcessingResult:
        res = ProcessingResult(ok=False, job_id=job_id)
        src = Path(video_path)
        if not src.exists():
            res.errors.append(f"source video not found: {video_path}")
            return res
        if not self.ffmpeg:
            res.errors.append("ffmpeg is not installed; cannot process video")
            return res

        workdir = self.root / job_id
        workdir.mkdir(parents=True, exist_ok=True)
        frames_dir = workdir / "frames"
        frames_dir.mkdir(exist_ok=True)
        res.frames_dir = str(frames_dir)

        try:
            duration = self._probe_duration(src)
            res.duration_sec = duration

            # 1) normalize -> H.264/AAC faststart mp4
            normalized = workdir / "normalized.mp4"
            p = self._run([self.ffmpeg, "-y", "-i", str(src),
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", "-b:a", "128k",
                           "-movflags", "+faststart", str(normalized)])
            if p.returncode != 0 or not normalized.exists():
                res.errors.append(f"normalize failed: {p.stderr[-400:]}")
                return res
            res.normalized_path = str(normalized)

            # 2) audio: 16 kHz mono wav for STT
            audio = workdir / "audio_16k.wav"
            p = self._run([self.ffmpeg, "-y", "-i", str(normalized),
                           "-ac", "1", "-ar", "16000", "-vn", str(audio)])
            if p.returncode == 0 and audio.exists():
                res.audio_path = str(audio)
            else:
                res.warnings.append("audio extraction failed; speech stage will be skipped")

            # 3) frames at 1 fps (capped)
            if duration and duration > 0:
                fps = min(1.0, max_frames / duration)
            else:
                fps = 1.0
            p = self._run([self.ffmpeg, "-y", "-i", str(normalized),
                           "-vf", f"fps={fps:.3f}", "-q:v", "4",
                           str(frames_dir / "frame_%04d.jpg")])
            if p.returncode == 0:
                res.frame_files = sorted(str(f) for f in frames_dir.glob("frame_*.jpg"))
            else:
                res.warnings.append("frame extraction failed; vision stage will be degraded")

            # 4) scene detection (timestamps of scene cuts)
            p = self._run([self.ffmpeg, "-i", str(normalized),
                           "-filter:v", "select='gt(scene,0.4)',showinfo",
                           "-f", "null", "-"], timeout=900)
            scenes: list[float] = []
            for line in (p.stderr or "").splitlines():
                if "pts_time:" in line:
                    try:
                        token = [t for t in line.split() if t.startswith("pts_time:")][0]
                        scenes.append(float(token.split(":")[1]))
                    except (IndexError, ValueError):
                        continue
            cuts = sorted(set(scenes))
            bounds = [0.0] + cuts + ([duration] if duration else [])
            res.segments = [
                {"start": round(bounds[i], 2), "end": round(bounds[i + 1], 2),
                 "scene_change": True}
                for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]
            ]

            # 5) thumbnails: 3 evenly spread
            thumbs: list[str] = []
            if duration and duration > 1:
                for n, frac in enumerate((0.15, 0.5, 0.85)):
                    thumb = workdir / f"thumb_{n}.jpg"
                    p = self._run([self.ffmpeg, "-y", "-ss", f"{duration * frac:.1f}",
                                   "-i", str(normalized), "-frames:v", "1",
                                   "-q:v", "5", str(thumb)], timeout=60)
                    if p.returncode == 0 and thumb.exists():
                        thumbs.append(str(thumb))
            elif res.frame_files:
                thumbs = res.frame_files[:1]
            res.thumbnails = thumbs

            res.ok = True
            log.info("process ok job=%s duration=%s frames=%d segments=%d",
                     job_id, duration, len(res.frame_files), len(res.segments))
        except subprocess.TimeoutExpired:
            res.errors.append("ffmpeg timed out during processing")
        except Exception as exc:  # never crash the worker
            log.exception("processing failed job=%s", job_id)
            res.errors.append(f"processing crashed: {exc}")
        return res
