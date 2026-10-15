"""
Database engine + session factory.

Uses DATABASE_URL when set (Supabase PostgreSQL in production), otherwise a
local SQLite file — dev/test fallback only. SQLite connections from the pool
are serialized for thread safety.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.database.models import Base

log = logging.getLogger("database")

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _sqlite_url() -> str:
    root = Path(get_settings().STORAGE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{root / 'recap.db'}"


def get_database_url() -> str:
    url = (get_settings().DATABASE_URL or "").strip()
    if url:
        # SQLAlchemy maps a bare "postgresql://" / "postgres://" URL to the
        # psycopg2 dialect, but this project pins psycopg v3
        # (psycopg[binary]) and has no psycopg2 dependency. Rewrite the
        # scheme so the v3 driver is used; no new dependency needed.
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        elif url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        return url
    log.warning("DATABASE_URL not set — using local SQLite dev fallback")
    return _sqlite_url()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_database_url()
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)

        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - sqlite only
            try:
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA busy_timeout=5000;")
                cur.close()
            except Exception:
                pass

    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db():
    """FastAPI dependency: yields a session, commits/rolls back per request."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Create all tables. Dev/test bootstrap (production uses migrations)."""
    Base.metadata.create_all(get_engine())
    log.info("database tables created")


def reset_engine_cache() -> None:
    """Test helper: drop cached engine/session so a new DATABASE_URL takes effect."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


__all__ = [
    "get_engine",
    "get_session_factory",
    "get_db",
    "create_all",
    "reset_engine_cache",
    "get_database_url",
]
