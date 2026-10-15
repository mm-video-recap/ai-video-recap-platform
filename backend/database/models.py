"""
SQLAlchemy 2 models for the AI Video Recap Platform.

All tables use UUID string primary keys so rows can be created safely by
both the FastAPI process and Celery workers without sequence conflicts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# JSON column that works on both PostgreSQL (JSONB) and SQLite (JSON)
JsonCol = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    videos: Mapped[list["Video"]] = relationship(back_populates="user")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), index=True, nullable=False
    )
    original_name: Mapped[str | None] = mapped_column(String(512))
    container: Mapped[str | None] = mapped_column(String(16))
    # BigInteger: MAX_UPLOAD_BYTES default is 2 GiB = 2,147,483,648, which is
    # 1 over the Postgres int (int4) max 2,147,483,647 — an int column would
    # reject a max-size upload at insert time. Migration 001 uses bigint.
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    sha256_prefix: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JsonCol, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="videos")
    jobs: Mapped[list["Job"]] = relationship(back_populates="video")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    video_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("videos.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), index=True, nullable=False
    )
    # queued | processing | analyzing | rendering | completed | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    output_lang: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    # Upload-time recap preferences (frontend upload form): persisted so the
    # pipeline and the job view can honour/show them instead of silently
    # dropping them. subtitle_language: my | en | none; recap_style:
    # concise | detailed | highlights.
    subtitle_language: Mapped[str] = mapped_column(String(8), default="my", nullable=False)
    recap_style: Mapped[str] = mapped_column(String(32), default="detailed", nullable=False)
    result: Mapped[dict] = mapped_column(JsonCol, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    video: Mapped["Video"] = relationship(back_populates="jobs")
    user: Mapped["User"] = relationship(back_populates="jobs")
    outputs: Mapped[list["Output"]] = relationship(back_populates="job")


class Output(Base):
    __tablename__ = "outputs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jobs.id"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # recap_video | subtitles | thumbnail | report
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    download_url: Mapped[str | None] = mapped_column(String(1024))
    # BigInteger: see Video.size_bytes (a max-size recap can exceed int4 max).
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="outputs")


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    task: Mapped[str | None] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmailRecord(Base):
    __tablename__ = "email_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="log", nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..3
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class BugReport(Base):
    __tablename__ = "bug_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class FeatureRequest(Base):
    __tablename__ = "feature_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    # healthy | degraded | unhealthy | unconfigured | unknown
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_rate: Mapped[float | None] = mapped_column(Float)
    last_error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CommunityWorker(Base):
    __tablename__ = "community_workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    worker_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capabilities: Mapped[dict] = mapped_column(JsonCol, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="online", nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ErrorLog(Base):
    __tablename__ = "error_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JsonCol, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


__all__ = [
    "Base",
    "User",
    "Video",
    "Job",
    "Output",
    "ApiUsage",
    "EmailRecord",
    "Feedback",
    "BugReport",
    "FeatureRequest",
    "ProviderHealth",
    "CommunityWorker",
    "ErrorLog",
    "AnalyticsEvent",
]
