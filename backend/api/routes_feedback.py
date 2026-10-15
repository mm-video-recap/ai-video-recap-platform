"""Feedback + bug reports + feature requests."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, log_event
from backend.api.schemas import (
    BugReportIn,
    FeatureRequestIn,
    FeedbackIn,
    OkResponse,
    ReportResponse,
)
from backend.database import BugReport, FeatureRequest, Feedback, Job, User, get_db

router = APIRouter(tags=["feedback"])


@router.post("/api/feedback", response_model=OkResponse)
def submit_feedback(body: FeedbackIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    job = db.query(Job).filter_by(id=body.job_id).one_or_none()
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Job not found")
    db.add(Feedback(user_id=user.id, job_id=body.job_id,
                    rating=body.rating, comment=body.comment))
    db.commit()
    log_event(db, user.id, "feedback_submitted", job_id=body.job_id,
              rating=body.rating)
    return OkResponse()


@router.post("/api/reports/bug", response_model=ReportResponse)
def report_bug(body: BugReportIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if body.job_id:
        job = db.query(Job).filter_by(id=body.job_id).one_or_none()
        if job is None or (job.user_id != user.id and not user.is_admin):
            raise HTTPException(status_code=404, detail="Job not found")
    rep = BugReport(user_id=user.id, subject=body.subject, body=body.body,
                    job_id=body.job_id)
    db.add(rep)
    db.commit()
    db.refresh(rep)
    log_event(db, user.id, "bug_reported", report_id=rep.id)
    return ReportResponse(id=rep.id)


@router.post("/api/reports/feature", response_model=ReportResponse)
def request_feature(body: FeatureRequestIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    req = FeatureRequest(user_id=user.id, title=body.title, body=body.body)
    db.add(req)
    db.commit()
    db.refresh(req)
    log_event(db, user.id, "feature_requested", report_id=req.id)
    return ReportResponse(id=req.id)
