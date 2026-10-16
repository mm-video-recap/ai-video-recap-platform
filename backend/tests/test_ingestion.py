"""Ingestion validation: bad extension/container and oversize uploads."""
import tempfile
from pathlib import Path

from backend.agents.agent01_ingestion import IngestionAgent


def _mp4(size: int = 2048) -> bytes:
    head = b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00" + b"\x00" * 64
    return head + b"\x00" * max(0, size - len(head))


def _write(suffix: str, data: bytes) -> Path:
    p = Path(tempfile.mkdtemp()) / f"file{suffix}"
    p.write_bytes(data)
    return p


def test_bad_extension_rejected():
    agent = IngestionAgent()
    p = _write(".txt", b"this is definitely not a video file at all" * 10)
    result = agent.ingest(p, "notes.txt", "u1")
    assert result.ok is False
    assert result.errors, "expected validation errors"
    assert any("nrecognized" in e or "upported" in e for e in result.errors)


def test_oversize_rejected():
    agent = IngestionAgent(max_bytes=100)  # tiny cap for the test
    p = _write(".mp4", _mp4(2048))
    result = agent.ingest(p, "big.mp4", "u1")
    assert result.ok is False
    assert any("too large" in e.lower() for e in result.errors)


def test_valid_mp4_accepted(monkeypatch):
    # Fixture file is ftyp magic + zeros: real ffprobe cannot read it,
    # and ingest now rejects files ffprobe cannot read. Patch probe
    # metadata to simulate a real, readable file.
    fake_meta = ({"duration_sec": 8.0, "video_codec": "h264",
                  "audio_codec": "aac", "has_audio": True,
                  "width": 640, "height": 360, "fps": 30.0}, True)
    monkeypatch.setattr(
        "backend.agents.agent01_ingestion._ffprobe_metadata",
        lambda p: fake_meta)
    agent = IngestionAgent()
    p = _write(".mp4", _mp4(4096))
    result = agent.ingest(p, "clip.mp4", "u1")
    assert result.ok is True, result.errors
    assert result.container == "mp4"
    assert result.job_id and result.video_id
