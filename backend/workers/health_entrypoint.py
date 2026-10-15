"""Worker entrypoint: Celery worker (+ embedded Beat) with an HTTP health server.

Why this exists
----------------
Hosts without a background-worker service type (e.g. Render free) run the
worker as a *web* service: the platform assigns a $PORT and expects the
container to bind it and answer HTTP health checks, or the deploy fails.
This entrypoint serves GET / and /health on $PORT (default 8000) while the
Celery worker runs in a child process.

Beat
----
Celery Beat runs embedded in the worker (``celery worker -B``) only when
``EMBED_BEAT=1``. Local Compose leaves it unset and runs Beat as its own
service (see docker-compose.yml), so periodic tasks are never scheduled
twice. On Render, set ``EMBED_BEAT=1`` on the worker service.

Signals: SIGTERM/SIGINT are forwarded to the worker (terminate), then the
entrypoint exits with the worker's exit code.
"""

import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

QUEUES = (
    "video_upload_queue,video_processing_queue,ai_analysis_queue,"
    "render_queue,email_queue"
)


def build_celery_command() -> list:
    """Celery worker command; appends ``-B`` (embedded Beat) iff EMBED_BEAT=1."""
    cmd = [
        "celery",
        "-A",
        "backend.celery_app.celery",
        "worker",
        "-Q",
        QUEUES,
    ]
    if os.environ.get("EMBED_BEAT") == "1":
        cmd.append("-B")
    return cmd


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint: 200 on / and /health, 404 otherwise."""

    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # keep health checks out of stdout
        pass


def main() -> int:
    port = int(os.environ.get("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    proc = subprocess.Popen(build_celery_command())

    def _forward(_signum, _frame):
        proc.terminate()

    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)

    rc = proc.wait()
    server.shutdown()
    return rc


if __name__ == "__main__":
    sys.exit(main())
