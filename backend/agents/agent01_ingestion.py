"""
Agent 01 — Video Ingestion Agent.

Responsibilities (per master spec):
- Validate the uploaded file (magic bytes + container sniffing + ffprobe)
- Check format (mp4 / mov / webm / mkv)
- Check size (free-tier cap)
- Create the job ID
- Save metadata

Real implementation. Works without FFmpeg (magic-byte validation still runs;
ffprobe metadata is marked as degraded). Never raises on unexpected input —
returns a structured result with errors listed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("agents.ingestion")

SUPPORTED_CONTAINERS = ("mp4", "mov", "webm", "mkv")

# magic-byte signatures: (offset, bytes) -> container
_MAGIC: dict[str, list[tuple[int, bytes]]] = {
    "mp4": [(4, b"ftyp")],
    "mov": [(4, b"ftyp")],  # mov also uses ftyp; distinguished by brand below
    "webm": [(0, b"\x1a\x45\xdf\xa3")],
    "mkv": [(0, b"\x1a\x45\xdf\xa3")],
}

# ftyp major brands that identify QuickTime/MOV instead of MP4
_MOV_BRANDS = {b"qt  ", b"moov"}


def _sniff_container(path: Path) -> Optional[str]:
    """Best-effort container detection from magic bytes. Returns None if unknown."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    if len(head) < 12:
        return None
    # EBML (webm / mkv) — distinguish by DocType element when present
    if head[0:4] == b"\x1a\x45\xdf\xa3":
        doctype = head.find(b"webm")
        if 0 <= doctype < 256:
            return "webm"
        return "mkv"
    # ISO BMFF / QuickTime
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in _MOV_BRANDS:
            return "mov"
        return "mp4"
    return None


def _ffprobe_metadata(path: Path) -> tuple[dict, bool]:
    """Run ffprobe when available. Returns (metadata, ffprobe_used)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}, False
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30, check=False)
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("ffprobe failed for %s: %s", path, exc)
        return {}, False
    if proc.returncode != 0:
        log.warning("ffprobe non-zero exit for %s: %s", path, proc.stderr[:200])
        return {}, False
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}, False
    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    meta = {
        "duration_sec": _safe_float(fmt.get("duration")),
        "size_bytes": _safe_int(fmt.get("size")),
        "bit_rate": _safe_int(fmt.get("bit_rate")),
        "format_name": fmt.get("format_name"),
        "width": _safe_int(video.get("width")),
        "height": _safe_int(video.get("height")),
        "fps": _fps(video.get("avg_frame_rate")),
        "video_codec": video.get("codec_name"),
        "has_audio": bool(audio),
        "audio_codec": audio.get("codec_name"),
    }
    return meta, True


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fps(rate) -> Optional[float]:
    try:
        num, den = str(rate).split("/")
        den = float(den)
        return float(num) / den if den else None
    except (ValueError, AttributeError, ZeroDivisionError):
        return None


def _sha256(path: Path, limit: int = 64 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            if fh.tell() > limit:  # hash prefix only for huge files
                h.update(b"...truncated...")
                break
    return h.hexdigest()


@dataclass
class IngestionResult:
    ok: bool
    job_id: str
    video_id: str
    container: Optional[str]
    metadata: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class IngestionAgent:
    """Validates uploads and mints job/video IDs."""

    def __init__(self, max_bytes: int = 2 * 1024 * 1024 * 1024,
                 max_duration_sec: int = 1800):
        self.max_bytes = max_bytes
        self.max_duration_sec = max_duration_sec

    def ingest(self, file_path: str | Path, original_name: str,
               user_id: str) -> IngestionResult:
        job_id = str(uuid.uuid4())
        video_id = str(uuid.uuid4())
        path = Path(file_path)
        errors: list[str] = []
        warnings: list[str] = []

        log.info("ingest job=%s user=%s file=%s", job_id, user_id, original_name)

        if not path.exists():
            errors.append(f"Uploaded file not found: {original_name}")
            return IngestionResult(False, job_id, video_id, None, {}, errors, warnings)

        size = path.stat().st_size
        if size == 0:
            errors.append("Uploaded file is empty")
        elif size > self.max_bytes:
            errors.append(
                f"File too large: {size / 1e9:.2f} GB exceeds "
                f"{self.max_bytes / 1e9:.0f} GB free-tier limit")

        container = _sniff_container(path)
        if container is None:
            errors.append(
                f"Unsupported or unrecognized container for '{original_name}'. "
                f"Supported: {', '.join(SUPPORTED_CONTAINERS)}")
        elif container not in SUPPORTED_CONTAINERS:
            errors.append(f"Container '{container}' is not supported")

        metadata: dict = {
            "original_name": original_name,
            "size_bytes": size,
            "sha256_prefix": _sha256(path) if path.exists() and size else None,
            "container": container,
            "user_id": user_id,
        }

        probe_meta, used = _ffprobe_metadata(path)
        metadata.update(probe_meta)
        metadata["ffprobe_used"] = used
        if not used:
            if shutil.which("ffprobe"):
                # ffprobe exists but could not read THIS file — the file
                # is corrupt or truncated. Fail fast at ingest with a
                # clear message instead of dying later at normalize with
                # a cryptic FFmpeg error (live 2026-10-16: every retry
                # failed at normalize within seconds).
                errors.append(
                    "File appears corrupt or truncated: ffprobe could not "
                    "read it. Re-save / re-export the video and upload again.")
            else:
                warnings.append("ffprobe unavailable; container metadata is approximate")

        duration = probe_meta.get("duration_sec")
        if duration and duration > self.max_duration_sec:
            errors.append(
                f"Video too long: {duration:.0f}s exceeds "
                f"{self.max_duration_sec}s free-tier limit")

        ok = not errors
        if ok:
            log.info("ingest ok job=%s container=%s duration=%s",
                     job_id, container, duration)
        else:
            log.warning("ingest rejected job=%s errors=%s", job_id, errors)
        return IngestionResult(ok, job_id, video_id, container, metadata, errors, warnings)


# ---------------------------------------------------------------------------
# Persistence helper (extension for the platform pipeline)
# ---------------------------------------------------------------------------
def persist_ingestion(db, result: "IngestionResult", *, user_id: str,
                      storage_path: str, output_lang: str = "en",
                      subtitle_language: str = "my",
                      recap_style: str = "detailed",
                      intro_enabled: bool = True,
                      outro_enabled: bool = True,
                      transcription_provider: str = "auto",
                      transcription_key_enc: str = "",
                      priority: int = 3) -> tuple:
    """
    Create the Video + Job rows for a successful ingestion.

    Returns (video, job). Never called with a failed result — raises
    ValueError in that case so callers surface validation errors as 400s.
    """
    if not result.ok:
        raise ValueError("; ".join(result.errors) or "ingestion failed")

    # Local import: keeps agent01 importable without SQLAlchemy installed.
    from backend.database.models import Job, Video  # noqa: PLC0415

    meta = dict(result.metadata)
    video = Video(
        id=result.video_id,
        user_id=user_id,
        original_name=meta.get("original_name"),
        container=result.container,
        size_bytes=meta.get("size_bytes"),
        duration_sec=meta.get("duration_sec"),
        width=meta.get("width"),
        height=meta.get("height"),
        storage_path=storage_path,
        sha256_prefix=meta.get("sha256_prefix"),
        meta={k: v for k, v in meta.items()
              if k not in {"original_name", "size_bytes", "duration_sec",
                           "width", "height", "sha256_prefix", "user_id"}},
    )
    # Intro/outro toggles live in video.meta (JSON) so no schema
    # migration is needed; missing keys mean "enabled" (backward compat).
    video.meta = {**(video.meta or {}),
                  "intro_enabled": bool(intro_enabled),
                  "outro_enabled": bool(outro_enabled),
                  "transcription_provider": transcription_provider,
                  "transcription_key_enc": transcription_key_enc}
    job = Job(
        id=result.job_id,
        video_id=result.video_id,
        user_id=user_id,
        status="queued",
        stage="ingested",
        progress=0.0,
        priority=priority,
        output_lang=output_lang,
        subtitle_language=subtitle_language,
        recap_style=recap_style,
    )
    db.add(video)
    db.add(job)
    db.flush()
    log.info("persisted video=%s job=%s", video.id, job.id)
    return video, job
