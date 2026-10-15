"""
Regression test: a bare postgresql:// DATABASE_URL (the Supabase format)
must resolve to the psycopg v3 driver, not psycopg2 (which is not installed).

Live incident 2026-10-15: the Railway deploy crashed at startup with
ModuleNotFoundError: No module named 'psycopg2' because SQLAlchemy maps a
bare postgresql:// URL to the psycopg2 dialect, while requirements.txt
pins psycopg[binary] (v3) only. get_database_url() now rewrites the
scheme to postgresql+psycopg://.
"""
import os

import pytest

from backend.config import get_settings
from backend.database.session import get_engine, reset_engine_cache


@pytest.fixture(autouse=True)
def _reset_engine():
    reset_engine_cache()
    yield
    reset_engine_cache()


def _engine_for(url: str):
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        return get_engine()
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()
        reset_engine_cache()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@db.example.com:5432/postgres",
        "postgres://user:pass@db.example.com:5432/postgres",
        "postgresql+psycopg://user:pass@db.example.com:5432/postgres",
    ],
)
def test_postgres_url_uses_psycopg_v3_driver(url):
    engine = _engine_for(url)
    assert engine.dialect.driver == "psycopg"
    assert engine.url.drivername == "postgresql+psycopg"


def test_sqlite_url_untouched():
    engine = _engine_for("sqlite:////tmp/recap_test_scheme.db")
    assert engine.dialect.driver == "pysqlite"
