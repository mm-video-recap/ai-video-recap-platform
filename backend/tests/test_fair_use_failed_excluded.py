"""Failed uploads must not consume the daily fair-use quota.

Live 2026-10-16: 5 failed uploads exhausted the 5/day cap with zero
recaps produced, locking the user out until tomorrow. A video counts
toward the cap only when it has at least one job that has not failed.
"""
import pytest

from backend.agents.agent01_ingestion import IngestionAgent
from backend.api.deps import FairUseExceeded, check_fair_use
from backend.config import get_settings
from backend.database import Job, User, Video


def _db_with_video(status: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.database import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(id="u1", email="u1@dev.local")
    db.add(user)
    db.add(Video(id="v1", user_id="u1", original_name="a.mp4",
                 duration_sec=60))
    db.add(Job(id="j1", video_id="v1", user_id="u1", status=status))
    db.commit()
    return db, user


def test_failed_job_video_does_not_count():
    db, user = _db_with_video("failed")
    settings = get_settings()
    # MAX_UPLOADS_PER_DAY is 5 in defaults; even with 5 failed videos the
    # cap must not trip — use a tight override instead.
    settings.MAX_UPLOADS_PER_DAY = 1
    check_fair_use(db, user, settings)  # must not raise


def test_processing_job_video_counts():
    db, user = _db_with_video("processing")
    settings = get_settings()
    settings.MAX_UPLOADS_PER_DAY = 1
    with pytest.raises(FairUseExceeded):
        check_fair_use(db, user, settings)


def test_ingest_rejects_file_ffprobe_cannot_read(monkeypatch, tmp_path):
    # ffprobe binary exists but cannot read THIS file -> hard error,
    # not a warning. Previously ingest passed such files and every
    # process_video retry died at normalize with a cryptic message.
    monkeypatch.setattr(
        "backend.agents.agent01_ingestion._ffprobe_metadata",
        lambda p: ({}, False))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffprobe")
    f = tmp_path / "broken.mp4"
    f.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 5000)
    result = IngestionAgent().ingest(f, "broken.mp4", "u1")
    assert not result.ok
    assert any("corrupt or truncated" in e for e in result.errors)


def test_ingest_still_warns_when_ffprobe_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.agents.agent01_ingestion._ffprobe_metadata",
        lambda p: ({}, False))
    monkeypatch.setattr("shutil.which", lambda name: None)
    f = tmp_path / "ok.mp4"
    f.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 5000)
    result = IngestionAgent().ingest(f, "ok.mp4", "u1")
    assert result.ok
    assert any("ffprobe unavailable" in w for w in result.warnings)
