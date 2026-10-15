"""
FastAPI application entrypoint: `uvicorn backend.main:app`.

Auth: Supabase JWT via `Authorization: Bearer <token>` (see security/jwt.py).
Dev-only escape hatch: ENV=development + DEV_AUTH_BYPASS=1 accepts
`Authorization: Bearer dev-token-<user-id>`. Default OFF — never enable in
production.

CORS: EXACT origins only. Any wildcard (`*`) in CORS_ORIGINS raises
ValueError at startup — a wildcard origin combined with
allow_credentials=True would let any matching subdomain make credentialed
API requests. Production must list the exact deployed frontend origin(s).
"""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.api import routes_admin, routes_auth, routes_feedback, routes_jobs
from backend.api import routes_results, routes_videos, routes_workers
from backend.api.rate_limit import limiter
from backend.config import get_settings

log = logging.getLogger("api.main")

settings = get_settings()


def build_cors_options(origins: list[str]) -> dict:
    """
    Build CORSMiddleware kwargs from an explicit origin allowlist.

    Raises ValueError if ANY origin contains a wildcard — wildcards must
    never be combined with allow_credentials=True (any matching subdomain
    could then make credentialed cross-origin requests). Never passes
    allow_origin_regex: only exact origins are allowed.
    """
    cleaned = [o.strip() for o in origins if o and o.strip()]
    wildcards = [o for o in cleaned if "*" in o]
    if wildcards:
        raise ValueError(
            "CORS_ORIGINS must list EXACT origins — wildcard origins are "
            f"rejected with credentials enabled: {wildcards}. Set the exact "
            "deployed frontend origin(s), e.g. "
            "CORS_ORIGINS=https://myan-recap.pages.dev"
        )
    return {
        "allow_origins": cleaned,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def _check_database() -> bool:
    """True when a trivial DB query succeeds. Never leaks error details."""
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from backend.database import get_engine  # noqa: PLC0415

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        log.debug("readiness: database check failed: %s", exc)
        return False


def _check_redis() -> bool:
    """True when the Celery broker answers PING. Never leaks error details."""
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        log.debug("readiness: redis check failed: %s", exc)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENV == "development":
        from backend.database import create_all  # noqa: PLC0415
        create_all()
        log.info("dev startup: database tables ensured")
    if settings.ENV == "production":
        if "localhost" in (settings.API_BASE_URL or "") or "127.0.0.1" in (
                settings.API_BASE_URL or ""):
            log.warning(
                "PRODUCTION MISCONFIG: API_BASE_URL still points at localhost "
                "(%s). Email links and download-URL fallbacks will be wrong — "
                "set API_BASE_URL to the public backend URL.",
                settings.API_BASE_URL)
        if settings.DEV_AUTH_BYPASS:
            log.warning(
                "PRODUCTION MISCONFIG: DEV_AUTH_BYPASS is enabled — disable it "
                "(DEV_AUTH_BYPASS=0).")
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
              lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429,
                        content={"detail": "Rate limit exceeded. Slow down — the service is free."})


# -- CORS: exact origins only (wildcards raise in build_cors_options) --------
app.add_middleware(CORSMiddleware, **build_cors_options(settings.CORS_ORIGINS))


# -- routes ------------------------------------------------------------------
@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/ready")
@app.get("/api/ready")
def readiness():
    """
    Readiness probe for orchestrators / load balancers.

    Returns 200 + {"status": "ready"} only when BOTH the database and Redis
    answer; otherwise 503 + {"status": "degraded"} with a per-check
    ok/error map. No internals (no exception text, hosts, or paths) leak
    into the response.
    """
    db_ok = _check_database()
    redis_ok = _check_redis()
    ready = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "degraded",
                 "checks": {"database": "ok" if db_ok else "error",
                            "redis": "ok" if redis_ok else "error"}})


app.include_router(routes_auth.router)
app.include_router(routes_videos.router)
app.include_router(routes_jobs.router)
app.include_router(routes_results.router)
app.include_router(routes_feedback.router)
app.include_router(routes_admin.router)
app.include_router(routes_workers.router)


# -- startup handled by lifespan above --------------------------------------------


__all__ = ["app", "limiter", "build_cors_options"]
