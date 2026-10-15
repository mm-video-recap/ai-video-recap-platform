"""Tests for backend/workers/health_entrypoint.py.

Covers: the EMBED_BEAT flag in the Celery command, and the HTTP health
endpoint (200 on / and /health, 404 elsewhere) over a real local socket.
Does NOT start Celery itself.
"""

import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

from backend.workers import health_entrypoint


def _serve_once():
    """Start the health server on an ephemeral port; return (server, port)."""
    server = HTTPServer(("127.0.0.1", 0), health_entrypoint.HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_command_without_embed_beat(monkeypatch):
    monkeypatch.delenv("EMBED_BEAT", raising=False)
    cmd = health_entrypoint.build_celery_command()
    assert cmd[:4] == ["celery", "-A", "backend.celery_app.celery", "worker"]
    assert "-B" not in cmd
    assert "video_upload_queue" in cmd[cmd.index("-Q") + 1]


def test_command_with_embed_beat(monkeypatch):
    monkeypatch.setenv("EMBED_BEAT", "1")
    assert "-B" in health_entrypoint.build_celery_command()


def test_command_embed_beat_ignores_other_values(monkeypatch):
    monkeypatch.setenv("EMBED_BEAT", "true")
    assert "-B" not in health_entrypoint.build_celery_command()


def test_health_endpoint_ok():
    server, port = _serve_once()
    try:
        assert _get(port, "/health") == (200, b"ok")
        assert _get(port, "/") == (200, b"ok")
    finally:
        server.shutdown()


def test_health_endpoint_unknown_path_404():
    server, port = _serve_once()
    try:
        status, _ = _get(port, "/nope")
        assert status == 404
    finally:
        server.shutdown()
