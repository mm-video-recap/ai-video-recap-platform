"""broker_reachable() must use the FULL broker URL (password included).

Live incident 2026-10-16: the old implementation built a client from
host/port alone, dropping the password, so password-protected Railway
Redis answered NOAUTH and enqueue skipped every job as "broker
unreachable" — uploads returned 201 but no worker task ever started,
while /ready (which uses from_url) reported redis ok.
"""
import redis

from backend.celery_app.tasks import broker_reachable


class _FakeClient:
    def __init__(self, url):
        self.url = url

    def ping(self):
        return True

    def close(self):
        pass


def test_broker_reachable_uses_full_url_with_password(monkeypatch):
    seen = {}

    def _from_url(url, **kwargs):
        seen["url"] = url
        return _FakeClient(url)

    monkeypatch.setattr(redis.Redis, "from_url", _from_url)

    class _Settings:
        CELERY_BROKER_URL = "redis://default:s3cretpass@redis-host:6380/2"

    monkeypatch.setattr("backend.config.get_settings",
                        lambda: _Settings())

    assert broker_reachable() is True
    # The password (and db index) must survive — the old code dropped them.
    assert seen["url"] == "redis://default:s3cretpass@redis-host:6380/2"


def test_broker_reachable_false_on_connection_error(monkeypatch):
    def _from_url(url, **kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(redis.Redis, "from_url", _from_url)

    class _Settings:
        CELERY_BROKER_URL = "redis://localhost:6399/0"

    monkeypatch.setattr("backend.config.get_settings",
                        lambda: _Settings())

    assert broker_reachable() is False
