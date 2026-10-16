"""
Provider manager: Gemini key rotation on 429, and the fallback chain
(gemini 503 -> groq succeeds) — all via httpx MockTransport, no network.
"""
import asyncio
import json

import httpx
import pytest

from backend.ai_provider.manager import GeminiProvider, ProviderError, ProviderManager
from backend.config import Settings


def _gemini_ok_body(text: str = "hello recap") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _groq_ok_body(text: str = "groq answered") -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_gemini_rotates_key_on_429(monkeypatch):
    """First key 429s -> manager rotates to GEMINI_KEY_01 and succeeds."""
    monkeypatch.setenv("GEMINI_API_KEY", "KEY_ONE")
    monkeypatch.setenv("GEMINI_KEY_01", "KEY_TWO")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.params.get("key")
        calls.append(key)
        if key == "KEY_ONE":
            return httpx.Response(429, json={"error": {"message": "quota exceeded"}})
        return httpx.Response(200, json=_gemini_ok_body())

    manager = ProviderManager(Settings(),
                              transports={"gemini": httpx.MockTransport(handler)})
    text, provider = asyncio.run(
        manager.complete("summary", "summarize this", user_id="u1", job_id="j1"))
    assert provider == "gemini"
    assert text == "hello recap"
    assert calls[0] == "KEY_ONE" and calls[-1] == "KEY_TWO", calls
    assert len(calls) >= 2, "expected rotation to the second key"


def test_fallback_chain_gemini_503_then_groq_succeeds(monkeypatch):
    """Gemini 503s on all keys -> router falls through to groq."""
    monkeypatch.setenv("GEMINI_API_KEY", "GEMINI_KEY")
    monkeypatch.setenv("GROQ_API_KEY", "GROQ_KEY")

    def gemini_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "high demand"}})

    def groq_handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        assert auth == "Bearer GROQ_KEY", auth
        return httpx.Response(200, json=_groq_ok_body())

    manager = ProviderManager(Settings(), transports={
        "gemini": httpx.MockTransport(gemini_handler),
        "groq": httpx.MockTransport(groq_handler),
    })
    text, provider = asyncio.run(
        manager.complete("summary", "summarize this", user_id="u1", job_id="j1"))
    assert provider == "groq", provider
    assert text == "groq answered"


def test_all_providers_fail_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "K")
    monkeypatch.setenv("GROQ_API_KEY", "G")
    monkeypatch.setenv("OPENROUTER_API_KEY", "O")

    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    manager = ProviderManager(Settings(), transports={
        "gemini": httpx.MockTransport(fail),
        "groq": httpx.MockTransport(fail),
        "openrouter": httpx.MockTransport(fail),
    })
    with pytest.raises(Exception, match="all providers failed"):
        asyncio.run(manager.complete("summary", "x"))


def test_gemini_default_model_is_live():
    """gemini-2.0-flash was retired by Google (live 404, 2026-10-17);
    the default must be the model Google's own error told us to use."""
    from backend.config import Settings

    assert Settings.model_fields["GEMINI_MODEL"].default == "gemini-3.8-flash"


def test_gemini_health_check_hits_configured_model(monkeypatch):
    """Health check must verify the CONFIGURED model, not the model list
    (listing returned 200 while gemini-2.0-flash was already retired)."""
    import asyncio

    import httpx

    from backend.ai_provider.manager import GeminiProvider
    from backend.config import Settings

    seen_urls: list[str] = []

    def _ok(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"name": "models/gemini-3.8-flash"})

    def _gone(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(404, json={"error": {"code": 404}})

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    provider = GeminiProvider(Settings())
    provider._client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(_ok))
    healthy, _, err = asyncio.run(provider.health_check())
    assert healthy is True and err is None
    assert "/models/gemini-3.8-flash" in seen_urls[-1]
    assert "pageSize" not in seen_urls[-1]

    provider._client = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(_gone))
    healthy, _, err = asyncio.run(provider.health_check())
    assert healthy is False and err == "HTTP 404"


def test_quota_exhaustion_sets_cooldown(monkeypatch):
    """After all keys hit 429, the provider must enter a cooldown so the
    next call waits instead of instantly re-burning every key (live
    2026-10-17: 11 keys, 105 rotations, quota is per-project)."""
    import time as _time

    def _fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="You exceeded your current quota")

    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.delenv("GEMINI_API_KEY_01", raising=False)
    provider = GeminiProvider(Settings())
    provider._client = lambda **kw: httpx.AsyncClient(
        transport=httpx.MockTransport(_fail))
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    provider._sleep = _fake_sleep  # type: ignore[method-assign]
    with pytest.raises(ProviderError, match="all 1 keys exhausted"):
        asyncio.run(provider.generate_text("hi"))
    assert provider._quota_cooldown_until > _time.monotonic()
    assert sleeps == [2.0]  # brief pause between key rotations, no real wait


def test_next_call_waits_out_cooldown(monkeypatch):
    """A call arriving during cooldown waits (stubbed) before calling."""
    import time as _time

    def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "done"}]}}]})

    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    provider = GeminiProvider(Settings())
    provider._client = lambda **kw: httpx.AsyncClient(
        transport=httpx.MockTransport(_ok))
    provider._quota_cooldown_until = _time.monotonic() + 60.0
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    provider._sleep = _fake_sleep  # type: ignore[method-assign]
    out = asyncio.run(provider.generate_text("hi"))
    assert out == "done"
    assert sleeps and sleeps[0] == pytest.approx(60.0, abs=1.0)
