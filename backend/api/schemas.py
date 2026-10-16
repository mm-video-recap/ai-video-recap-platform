"""Pydantic request/response schemas for the API contract."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ auth
class MeResponse(BaseModel):
    id: str
    email: str | None
    is_admin: bool
    display_name: str | None


# ------------------------------------------------------------------ videos
class UploadResponse(BaseModel):
    video_id: str
    job_id: str
    estimated_seconds: int


class VideoSummary(BaseModel):
    id: str
    original_name: str | None
    container: str | None
    duration_sec: float | None
    size_bytes: int | None
    created_at: str
    latest_job: dict | None = None
    # Convenience fields for frontend list/detail rendering (derived, additive).
    title: str | None = None
    status: str = "uploaded"
    thumbnail_url: str | None = None


class VideoDetail(VideoSummary):
    width: int | None
    height: int | None
    sha256_prefix: str | None = None


# ------------------------------------------------------------------ jobs
class JobStatus(BaseModel):
    id: str
    status: str
    stage: str | None
    progress: float
    error: str | None
    # Upload-time recap preferences (persisted on the Job; see B15 fix).
    subtitle_language: str = "my"
    recap_style: str = "detailed"


# ------------------------------------------------------------------ results
class TimelineItem(BaseModel):
    start: float
    end: float
    label: str


class HighlightItem(BaseModel):
    start: float
    end: float
    score: float


class TranscriptItem(BaseModel):
    start: float
    end: float
    text: str


class ResultsResponse(BaseModel):
    download_url: str
    title: str
    description: str
    summary_short: str
    summary_long: str
    key_points: list[str]
    timeline: list[TimelineItem]
    highlights: list[HighlightItem]
    transcript: list[TranscriptItem]
    subtitle_url: str | None
    warnings: list[str] = []


# ------------------------------------------------------------------ feedback / reports
class FeedbackIn(BaseModel):
    job_id: str = Field(min_length=1)
    rating: int = Field(ge=1, le=3, description="1=bad, 2=ok, 3=great")
    comment: str | None = Field(default=None, max_length=2000)


class OkResponse(BaseModel):
    ok: bool = True


class BugReportIn(BaseModel):
    subject: str = Field(min_length=3, max_length=512)
    body: str = Field(min_length=3, max_length=10000)
    job_id: str | None = None


class FeatureRequestIn(BaseModel):
    title: str = Field(min_length=3, max_length=512)
    body: str = Field(min_length=3, max_length=10000)


class ReportResponse(BaseModel):
    ok: bool = True
    id: str


# ------------------------------------------------------------------ workers
class WorkerRegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    worker_type: str = Field(min_length=1, max_length=64)
    capabilities: dict = Field(default_factory=dict)


class WorkerRegisterOut(BaseModel):
    worker_id: str
