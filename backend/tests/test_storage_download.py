"""Shared-storage download: the worker must materialize uploads locally.

Live incident 2026-10-16: with local storage the API saved the upload
to ITS OWN container disk and the worker looked for the same path on
ITS OWN filesystem — every job failed at ingest with "uploaded file
missing". The storage interface now has download(), and ensure_local()
resolves a storage key to a local file.
"""
from pathlib import Path

import httpx

from backend.storage import ensure_local, get_storage, reset_storage_cache
from backend.storage.local import LocalStorage
from backend.storage.supabase_store import SupabaseStorage


def test_local_download_copies(tmp_path):
    store = LocalStorage(tmp_path)
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello")
    store.put(src, "uploads/v1/original.mp4")
    dest = tmp_path / "out" / "original.mp4"
    assert store.download("uploads/v1/original.mp4", dest) == dest
    assert dest.read_bytes() == b"hello"


def test_supabase_put_sends_upsert_and_logs_body(monkeypatch, tmp_path, caplog):
    import logging

    seen = {}

    class _Resp:
        status_code = 400
        text = '{"error":"Duplicate","message":"already exists"}'

        def raise_for_status(self):
            raise httpx.HTTPStatusError("400", request=None, response=self)

    def _post(url, **kwargs):
        seen["headers"] = kwargs["headers"]
        return _Resp()

    monkeypatch.setattr(httpx, "post", _post)
    store = SupabaseStorage("https://ref.supabase.co", "svc-key", "recap-results")
    src = tmp_path / "up.mp4"
    src.write_bytes(b"data")
    with caplog.at_level(logging.WARNING, logger="storage.supabase"):
        try:
            store.put(src, "uploads/v1/original.mp4")
            raise AssertionError("expected HTTPStatusError")
        except httpx.HTTPStatusError:
            pass
    assert seen["headers"]["x-upsert"] == "true"
    assert "already exists" in caplog.text


def test_supabase_put_rls_hint_when_anon_key_used(monkeypatch, tmp_path, caplog):
    import logging

    class _Resp:
        status_code = 400
        text = ('{"statusCode":"403","error":"Unauthorized","message":'
                '"new row violates row-level security policy"}')

        def raise_for_status(self):
            raise httpx.HTTPStatusError("400", request=None, response=self)

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    store = SupabaseStorage("https://ref.supabase.co", "anon-key", "recap-results")
    src = tmp_path / "up.mp4"
    src.write_bytes(b"data")
    with caplog.at_level(logging.WARNING, logger="storage.supabase"):
        try:
            store.put(src, "uploads/v1/original.mp4")
            raise AssertionError("expected HTTPStatusError")
        except httpx.HTTPStatusError:
            pass
    assert "anon key, not the service_role key" in caplog.text
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, size):
            yield b"ab"
            yield b"cd"

    def _stream(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/storage/v1/object/recap-results/uploads/v1/original.mp4")
        assert kwargs["headers"]["apikey"] == "svc-key"
        return _Resp()

    monkeypatch.setattr(httpx, "stream", _stream)
    store = SupabaseStorage("https://ref.supabase.co", "svc-key", "recap-results")
    dest = tmp_path / "original.mp4"
    assert store.download("uploads/v1/original.mp4", dest) == dest
    assert dest.read_bytes() == b"abcd"


def test_ensure_local_passthrough_for_existing_absolute_path(tmp_path):
    f = tmp_path / "already.mp4"
    f.write_bytes(b"x")
    assert ensure_local(str(f), "v1") == f


def test_ensure_local_downloads_key_with_local_provider(tmp_path, monkeypatch):
    # Local provider, key-style storage_path: resolves via LocalStorage.
    reset_storage_cache()
    store = get_storage()
    assert store.name == "local"
    root = Path(store.root)  # conftest STORAGE_ROOT (tmp)
    src = tmp_path / "up.mp4"
    src.write_bytes(b"data")
    store.put(src, "uploads/v9/original.mp4")
    got = ensure_local("uploads/v9/original.mp4", "v9")
    assert got == root / "uploads" / "v9" / "original.mp4"
    assert got.read_bytes() == b"data"
