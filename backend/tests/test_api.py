"""
API contract tests via TestClient (sqlite + DEV_AUTH_BYPASS, no network).
"""
import json


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_me(client, auth_headers):
    r = client.get("/api/auth/me", headers=auth_headers("u1"))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "u1"
    assert body["is_admin"] is False


def test_me_unauthorized(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 401


def test_upload_bad_file_rejected(client, auth_headers):
    files = {"file": ("notes.txt", b"not a video" * 100, "text/plain")}
    r = client.post("/api/videos/upload", files=files, headers=auth_headers("u2"))
    assert r.status_code == 400


def test_upload_creates_job(client, uploaded):
    r = client.get(f"/api/jobs/{uploaded['job_id']}", headers=uploaded["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == uploaded["job_id"]
    assert body["status"] in ("queued", "processing")
    assert body["progress"] >= 0


def test_videos_list_and_detail(client, uploaded):
    r = client.get("/api/videos", headers=uploaded["headers"])
    assert r.status_code == 200
    ids = [v["id"] for v in r.json()]
    assert uploaded["video_id"] in ids

    r = client.get(f"/api/videos/{uploaded['video_id']}", headers=uploaded["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == uploaded["video_id"]


def test_other_user_cannot_see_video(client, auth_headers, uploaded):
    assert client.get(f"/api/videos/{uploaded['video_id']}",
                      headers=auth_headers("stranger")).status_code == 404
    assert client.get(f"/api/jobs/{uploaded['job_id']}",
                      headers=auth_headers("stranger")).status_code == 404


def test_results_404_before_done(client, uploaded):
    r = client.get(f"/api/results/{uploaded['job_id']}", headers=uploaded["headers"])
    assert r.status_code == 404


def test_sse_stream_emits_events(client, uploaded):
    """Spin the real app under uvicorn in a thread (httpx's ASGI transport
    buffers streaming responses, so a real socket is needed for SSE)."""
    import socket
    import threading
    import time

    import httpx
    import uvicorn

    from backend.main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        # NOTE: trust_env=False — the sandbox's stock NO_PROXY contains
        # bracketed IPv6 literals ([::1]) that crash httpx's URL parser.
        for _ in range(100):  # wait for boot
            try:
                if httpx.get(f"{base}/api/health", timeout=1,
                             trust_env=False).status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)
        events = []
        with httpx.stream("GET",
                          f"{base}/api/jobs/{uploaded['job_id']}/stream",
                          params={"token": uploaded["token"]},
                          timeout=10.0, trust_env=False) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[len("data:"):]))
                    break
        assert events, "expected at least one SSE event"
        assert "stage" in events[0] and "progress" in events[0]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_feedback_validation(client, uploaded):
    _h = uploaded["headers"]
    # rating out of range -> 422
    r = client.post("/api/feedback",
                    json={"job_id": uploaded["job_id"], "rating": 4},
                    headers=_h)
    assert r.status_code == 422
    # valid -> ok
    r = client.post("/api/feedback",
                    json={"job_id": uploaded["job_id"], "rating": 3,
                          "comment": "great recap"},
                    headers=_h)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_reports(client, uploaded):
    _h = uploaded["headers"]
    r = client.post("/api/reports/bug",
                    json={"subject": "render stuck", "body": "it hung at 90%",
                          "job_id": uploaded["job_id"]},
                    headers=_h)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["id"]

    r = client.post("/api/reports/feature",
                    json={"title": "dark mode", "body": "please add dark mode"},
                    headers=_h)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["id"]


def test_admin_forbidden_for_non_admin(client, auth_headers):
    for path in ("/api/admin/overview", "/api/admin/jobs", "/api/admin/providers",
                 "/api/admin/feedback", "/api/admin/analytics", "/api/admin/errors"):
        assert client.get(path, headers=auth_headers("u1")).status_code == 403, path


def test_admin_overview_ok(client, admin_headers):
    r = client.get("/api/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("users", "jobs_active", "queue_depth", "providers", "storage"):
        assert key in body, key
    assert isinstance(body["queue_depth"], int), "queue_depth must be a number (per-queue in queue_depths)"
    r = client.get("/api/admin/analytics", headers=admin_headers)
    assert r.status_code == 200
    for key in ("daily_users", "processing_volume", "ai_usage", "errors"):
        assert key in r.json(), key


def test_service_token_auth(client, monkeypatch):
    """RECAP_API_SERVICE_TOKEN (n8n monitoring) -> service:n8n admin identity."""
    import os
    monkeypatch.setenv("RECAP_API_SERVICE_TOKEN", "svc-test-token")
    from backend.config import get_settings
    get_settings.cache_clear()
    try:
        # wrong token -> 401
        r = client.get("/api/admin/overview",
                       headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401
        # right token -> admin access
        r = client.get("/api/admin/overview",
                       headers={"Authorization": "Bearer svc-test-token"})
        assert r.status_code == 200, r.text
        r = client.get("/api/auth/me",
                       headers={"Authorization": "Bearer svc-test-token"})
        assert r.status_code == 200 and r.json()["id"] == "service:n8n"
    finally:
        monkeypatch.delenv("RECAP_API_SERVICE_TOKEN", raising=False)
        get_settings.cache_clear()


def test_worker_gateway(client):
    # no token -> 401
    r = client.post("/api/workers/register",
                    json={"name": "w1", "worker_type": "gpu",
                          "capabilities": {"ffmpeg": True}})
    assert r.status_code == 401
    # wrong token -> 401
    r = client.post("/api/workers/register",
                    json={"name": "w1", "worker_type": "gpu"},
                    headers={"X-Worker-Token": "wrong"})
    assert r.status_code == 401
    # right token -> registered
    r = client.post("/api/workers/register",
                    json={"name": "w1", "worker_type": "gpu",
                          "capabilities": {"ffmpeg": True}},
                    headers={"X-Worker-Token": "test-gateway-token"})
    assert r.status_code == 200
    worker_id = r.json()["worker_id"]
    # heartbeat
    r = client.post(f"/api/workers/{worker_id}/heartbeat",
                    headers={"X-Worker-Token": "test-gateway-token"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    # pull next task
    r = client.get("/api/workers/tasks/next",
                   headers={"X-Worker-Token": "test-gateway-token"})
    assert r.status_code == 200 and "task" in r.json()
