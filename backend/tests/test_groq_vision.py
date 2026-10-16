"""Groq free-tier vision fallback (live 2026-10-17: Gemini 429s killed vision)."""
import httpx
import pytest

from backend.ai_provider.manager import GroqProvider, ProviderError
from backend.config import Settings


def _provider(handler, keys=("k1",)):
    import os
    os.environ["GROQ_API_KEY"] = keys[0]
    settings = Settings()
    provider = GroqProvider(settings, transport=httpx.MockTransport(handler))
    provider._override_keys = list(keys)
    return provider


@pytest.mark.asyncio
async def test_groq_vision_returns_description(tmp_path):
    img = tmp_path / "f.jpg"
    img.write_bytes(b"fake-jpeg")

    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        body = httpx.QueryParams()  # noqa: F841 (shape check below uses json)
        import json as _json
        payload = _json.loads(request.content)
        assert payload["model"] == "qwen/qwen3.8-27b"
        content = payload["messages"][0]["content"]
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "a person speaking"}}]})

    out = await _provider(handler).analyze_image(img, "describe")
    assert out == {"description": "a person speaking"}


@pytest.mark.asyncio
async def test_groq_vision_rotates_key_on_429(tmp_path):
    img = tmp_path / "f.jpg"
    img.write_bytes(b"fake-jpeg")
    seen: list[str] = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        if len(seen) == 1:
            return httpx.Response(429, text="quota exceeded")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok after rotate"}}]})

    out = await _provider(handler, keys=("k1", "k2")).analyze_image(img, "describe")
    assert out == {"description": "ok after rotate"}
    assert seen == ["Bearer k1", "Bearer k2"]


@pytest.mark.asyncio
async def test_groq_vision_unconfigured_without_key(tmp_path, monkeypatch):
    import os
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY1", raising=False)
    monkeypatch.delenv("GROQ_API_KEY2", raising=False)
    settings = Settings()
    provider = GroqProvider(settings, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})))
    provider._override_keys = []
    with pytest.raises(ProviderError, match="not configured"):
        await provider.analyze_image(tmp_path / "f.jpg", "describe")
