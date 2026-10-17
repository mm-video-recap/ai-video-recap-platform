"""
Shared API dependencies: auth, admin gate, fair-use limits, analytics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database import AnalyticsEvent, ApiUsage, User, Video, get_db
from backend.security.jwt import (
    AuthError,
    AuthUnavailableError,
    AuthUser,
    InvalidTokenError,
    verify_jwt,
)

log = logging.getLogger("api.deps")


def _service_user_from_token(token: str, settings: Settings) -> AuthUser | None:
    """
    Machine-to-machine auth (n8n monitoring flow): when
    RECAP_API_SERVICE_TOKEN is set, a Bearer token equal to it authenticates
    as the service identity "service:n8n" with admin rights. Empty setting
    = disabled. Never log the token.
    """
    service_token = (settings.RECAP_API_SERVICE_TOKEN or "").strip()
    if service_token and token == service_token:
        return AuthUser(id="service:n8n", email="service@n8n.local",
                        role="service", is_admin=True)
    return None


def _dev_user_from_token(token: str, settings: Settings) -> AuthUser | None:
    """
    Dev/test escape hatch (documented, default OFF):
    ENV=development + DEV_AUTH_BYPASS=1 accepts
        Authorization: Bearer dev-token-<user-id>
    as that user. Never enabled in production.
    """
    if not (settings.ENV == "development" and settings.DEV_AUTH_BYPASS):
        return None
    if not token.startswith("dev-token-"):
        return None
    user_id = token[len("dev-token-"):].strip()
    if not user_id:
        return None
    email = user_id if "@" in user_id else f"{user_id}@dev.local"
    is_admin = email.lower() in settings.admin_email_set
    return AuthUser(id=user_id, email=email, role="authenticated", is_admin=is_admin)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    return token.strip()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    token = _bearer_token(authorization)

    auth_user: AuthUser | None = _service_user_from_token(token, settings)
    if auth_user is None:
        auth_user = _dev_user_from_token(token, settings)
    if auth_user is None:
        try:
            auth_user = verify_jwt(
                token,
                supabase_url=settings.SUPABASE_URL,
                jwt_secret=settings.SUPABASE_JWT_SECRET,
            )
        except (InvalidTokenError, AuthUnavailableError) as exc:
            # Log the REASON (never the token) — a bare 401 is
            # undiagnosable from Railway logs. Live incident 2026-10-16:
            # 103x 401 in ~22s with no visible cause.
            log.warning("JWT verification failed: %s", exc)
            raise HTTPException(status_code=401, detail=str(exc))
        except AuthError as exc:
            log.warning("JWT verification failed: %s", exc)
            raise HTTPException(status_code=401, detail=str(exc))

    # local admin override via ADMIN_EMAILS env
    is_admin = auth_user.is_admin or (
        auth_user.email or "").lower() in settings.admin_email_set

    user = db.query(User).filter_by(id=auth_user.id).one_or_none()
    if user is None:
        user = User(id=auth_user.id, email=auth_user.email,
                    display_name=(auth_user.email or "").split("@")[0] or None,
                    is_admin=is_admin)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Race: a concurrent first request for this user (the
            # dashboard fires /api/auth/me and /api/videos at once)
            # already inserted the row. Roll back and use it instead
            # of 500ing — live incident 2026-10-16: three 500s on
            # duplicate key "users_pkey" during cutover.
            db.rollback()
            user = db.query(User).filter_by(id=auth_user.id).one_or_none()
            if user is None:
                raise
        db.refresh(user)
    elif user.is_admin != is_admin:
        user.is_admin = is_admin
        db.commit()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def verify_query_token(token: str, settings: Settings) -> AuthUser:
    """Token verification for SSE (?token=<jwt>) — same rules as headers."""
    auth_user = _dev_user_from_token(token, settings)
    if auth_user is not None:
        return auth_user
    try:
        return verify_jwt(token, supabase_url=settings.SUPABASE_URL,
                          jwt_secret=settings.SUPABASE_JWT_SECRET)
    except AuthError as exc:
        log.warning("JWT verification failed (query token): %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))


# ---------------------------------------------------------------- fair use
class FairUseExceeded(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=429, detail=detail)


def _today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def is_owner(user: User) -> bool:
    """True only for the single owner account (OWNER_EMAIL setting).
    Only the owner may use the server (env) AI keys; everyone else
    must bring both their own Gemini + Groq keys."""
    return get_settings().is_owner(user.email)


def check_fair_use(db: Session, user: User, settings: Settings,
                   estimated_seconds: float | None = None) -> None:
    """Enforce the free-tier fair-use caps. Raises 429 when exceeded."""
    today = _today_utc()

    # Failed uploads do NOT consume quota: the user got no result, so
    # they can retry. Live 2026-10-16: 5 failed uploads exhausted the
    # daily cap with zero recaps produced. A video counts only when it
    # has at least one job that has not failed (queued / processing /
    # completed all count — they may still consume resources).
    from backend.database import Job  # noqa: PLC0415 - avoid import cycle
    from sqlalchemy import select  # noqa: PLC0415

    good_ids = (select(Job.video_id)
                .where(Job.status != "failed").distinct())
    uploads = db.query(Video).filter(
        Video.user_id == user.id, Video.created_at >= today,
        Video.id.in_(good_ids)).count()
    if uploads >= settings.MAX_UPLOADS_PER_DAY:
        raise FairUseExceeded(
            f"Daily upload limit reached ({settings.MAX_UPLOADS_PER_DAY}/day). "
            "Try again tomorrow — the service is 100% free.")

    if estimated_seconds:
        from sqlalchemy import func  # noqa: PLC0415
        total_sec = db.query(func.coalesce(func.sum(Video.duration_sec), 0)).filter(
            Video.user_id == user.id, Video.created_at >= today,
            Video.id.in_(good_ids)).scalar() or 0
        if (total_sec + estimated_seconds) / 60 > settings.MAX_PROCESSING_MINUTES_PER_DAY:
            raise FairUseExceeded(
                f"Daily processing limit reached "
                f"({settings.MAX_PROCESSING_MINUTES_PER_DAY} min/day).")

    ai_calls = db.query(ApiUsage).filter(
        ApiUsage.user_id == user.id, ApiUsage.created_at >= today).count()
    if ai_calls >= settings.MAX_AI_REQUESTS_PER_DAY:
        raise FairUseExceeded(
            f"Daily AI request limit reached ({settings.MAX_AI_REQUESTS_PER_DAY}/day).")


def log_event(db: Session, user_id: str | None, event: str, **payload) -> None:
    try:
        db.add(AnalyticsEvent(user_id=user_id, event=event, payload=payload))
        db.commit()
    except Exception as exc:
        log.warning("analytics log failed: %s", exc)
