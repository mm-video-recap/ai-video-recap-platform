"""
AI provider manager — owner-keys-only LLM routing with rotation + fallback.

Design
------
* Every AI call goes through `ProviderManager.complete(task, ...)` (text),
  `.transcribe(...)` (speech) or `.analyze_image(...)` (vision).
* Task -> provider order (per spec):
    summary            -> gemini, groq, openrouter
    transcript-analysis-> groq, gemini, openrouter
    backup             -> openrouter, groq, gemini
    vision             -> huggingface, gemini, openrouter
    speech             -> groq, huggingface
* Gemini rotates across GEMINI_API_KEY + GEMINI_KEY_01..03 on 429 / quota /
  503 errors. Each provider gets one retry with backoff, then the router
  moves to the next provider in the chain.
* All HTTP goes through httpx — no heavy vendor SDKs required.
* Every call is logged to ApiUsage (best effort; never crashes the caller).
* `health_check_all()` runs the 5-minute beat; results feed ProviderHealth.
* For unit tests, pass `transports={provider_name: httpx.MockTransport}`
  to the constructor to intercept outbound HTTP.

No user-supplied keys anywhere: keys come from env via Settings only.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from backend.config import Settings, get_settings

log = logging.getLogger("ai_provider")

# HTTP statuses that mean "try the next key / next provider"
RETRYABLE_KEY_ERRORS = {429, 503}
QUOTA_MARKERS = ("quota", "rate limit", "rate_limit", "resource_exhausted",
                 "insufficient_quota", "too many requests")

TASK_ROUTES: dict[str, list[str]] = {
    "summary": ["gemini", "groq", "openrouter"],
    "transcript-analysis": ["groq", "gemini", "openrouter"],
    "backup": ["openrouter", "groq", "gemini"],
    "vision": ["huggingface", "gemini", "openrouter"],
    "speech": ["groq", "huggingface"],
}


class ProviderError(Exception):
    """A provider call failed; carries whether the failure is retryable."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class AIProvider(ABC):
    name: str = "base"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    def _client(self, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", httpx.Timeout(120.0, connect=20.0))
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _configured(self, *keys: str) -> bool:
        return any(keys)

    @abstractmethod
    async def generate_text(self, prompt: str, *, model: str | None = None,
                            json_mode: bool = False, max_tokens: int = 2048) -> str:
        ...

    async def transcribe(self, audio_path: str | Path) -> dict:  # pragma: no cover
        raise ProviderError(f"{self.name} does not support transcription")

    async def analyze_image(self, image_path: str | Path, prompt: str) -> dict:  # pragma: no cover
        raise ProviderError(f"{self.name} does not support vision")

    @abstractmethod
    async def health_check(self) -> tuple[bool, int | None, str | None]:
        """Return (healthy, latency_ms, error_message)."""

    @staticmethod
    def _looks_like_quota(text: str, status: int | None) -> bool:
        lowered = (text or "").lower()
        return status in RETRYABLE_KEY_ERRORS or any(m in lowered for m in QUOTA_MARKERS)


# ---------------------------------------------------------------- Gemini
_GEMINI_TRANSCRIBE_PROMPT = (
    "Transcribe this audio verbatim. Return ONLY JSON: "
    '{"segments": [{"start": <seconds>, "end": <seconds>, "text": "<words>"}]}. '
    "Split into segments at natural pauses (each a few seconds long). "
    "Keep the original language; do not translate. "
    "Timestamps are relative to the START of this audio chunk."
)


def _split_wav_chunks(path: Path, chunk_sec: int) -> list[tuple[float, bytes]]:
    """Split a PCM WAV into <=chunk_sec pieces. Returns (offset_sec, bytes)
    with a full WAV header per piece. Non-WAV audio falls back to one
    chunk holding the whole file (Gemini still accepts it)."""
    try:
        import io
        import wave

        with wave.open(str(path), "rb") as wf:
            params = wf.getparams()
            rate = wf.getframerate() or 16000
            frame_bytes = max(1, wf.getnchannels() * wf.getsampwidth())
            frames_per_chunk = max(1, int(chunk_sec * rate))
            chunks: list[tuple[float, bytes]] = []
            offset = 0.0
            while True:
                frames = wf.readframes(frames_per_chunk)
                if not frames:
                    break
                buf = io.BytesIO()
                with wave.open(buf, "wb") as out:
                    out.setparams(params)
                    out.writeframes(frames)
                chunks.append((offset, buf.getvalue()))
                # readframes returns BYTES, not frames — divide by the
                # frame size or offsets drift 2x (1ch 16-bit).
                offset += (len(frames) // frame_bytes) / rate
            return chunks or [(0.0, path.read_bytes())]
    except Exception:
        return [(0.0, path.read_bytes())]


class GeminiProvider(AIProvider):
    name = "gemini"
    # Inline-audio chunk size for transcription (seconds of 16 kHz mono
    # WAV per generateContent call).
    _TRANSCRIBE_CHUNK_SEC = 300

    def __init__(self, settings: Settings, transport=None, keys: list[str] | None = None):
        super().__init__(settings, transport)
        # keys override: a per-user (BYOK) key for one job. When None, the
        # server env keys are used (settings.gemini_keys).
        self._keys: list[str] = list(keys) if keys is not None else settings.gemini_keys
        self._key_index: int = 0

    @property
    def configured(self) -> bool:
        return bool(self._keys)

    def _next_key(self) -> str:
        key = self._keys[self._key_index % len(self._keys)]
        return key

    def _rotate(self) -> None:
        self._key_index = (self._key_index + 1) % len(self._keys)
        log.info("gemini: rotated to key index %d", self._key_index)

    async def generate_text(self, prompt: str, *, model: str | None = None,
                            json_mode: bool = False, max_tokens: int = 2048) -> str:
        if not self.configured:
            raise ProviderError("gemini not configured (no API keys)")
        model = model or self.settings.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        last_exc: Exception | None = None
        for _ in range(len(self._keys)):
            key = self._next_key()
            try:
                async with self._client() as client:
                    resp = await client.post(url, params={"key": key}, json=body)
                if resp.status_code != 200:
                    if self._looks_like_quota(resp.text, resp.status_code):
                        log.warning("gemini key %d hit %s; rotating",
                                    self._key_index, resp.status_code)
                        self._rotate()
                        last_exc = ProviderError(resp.text[:300], status=resp.status_code,
                                                 retryable=True)
                        continue
                    raise ProviderError(f"gemini HTTP {resp.status_code}: {resp.text[:300]}",
                                        status=resp.status_code)
                data = resp.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if not text:
                    raise ProviderError("gemini returned empty response")
                return text
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_exc = exc
                self._rotate()
        raise ProviderError(f"gemini: all {len(self._keys)} keys exhausted: {last_exc}")

    async def analyze_image(self, image_path: str | Path, prompt: str) -> dict:
        if not self.configured:
            raise ProviderError("gemini not configured (no API keys)")
        raw = Path(image_path).read_bytes()
        b64 = base64.b64encode(raw).decode()
        model = self.settings.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
        ]}]}
        last_exc: Exception | None = None
        for _ in range(len(self._keys)):
            key = self._next_key()
            try:
                async with self._client() as client:
                    resp = await client.post(url, params={"key": key}, json=body)
                if resp.status_code != 200:
                    if self._looks_like_quota(resp.text, resp.status_code):
                        self._rotate()
                        last_exc = ProviderError(resp.text[:200], status=resp.status_code,
                                                 retryable=True)
                        continue
                    raise ProviderError(f"gemini vision HTTP {resp.status_code}")
                data = resp.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                return {"description": "".join(p.get("text", "") for p in parts).strip()}
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_exc = exc
                self._rotate()
        raise ProviderError(f"gemini vision: all keys exhausted: {last_exc}")

    async def transcribe(self, audio_path: str | Path) -> dict:
        """Transcribe audio with Gemini multimodal (audio in, JSON out).

        The extracted audio is 16 kHz mono WAV. Inline audio is sent in
        <=5-minute chunks (keeps each request small); segments are
        offset back to full-audio time. Raises ProviderError when the
        key is missing or every chunk fails.
        """
        if not self._keys:
            raise ProviderError("gemini not configured (no API keys)")
        chunks = _split_wav_chunks(Path(audio_path), self._TRANSCRIBE_CHUNK_SEC)
        segments: list[dict] = []
        for offset, chunk_bytes in chunks:
            text = await self._generate_with_audio(
                chunk_bytes, _GEMINI_TRANSCRIBE_PROMPT)
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"gemini transcription returned non-JSON: {text[:200]}") from exc
            for seg in data.get("segments", []) or []:
                try:
                    start = float(seg.get("start", 0)) + offset
                    end = float(seg.get("end", start)) + offset
                except (TypeError, ValueError):
                    continue
                if end <= start:
                    continue
                segments.append({"start": start, "end": end,
                                 "text": str(seg.get("text", "")).strip()})
        segments.sort(key=lambda s: s["start"])
        return {"transcript": segments, "language": None,
                "confidence": None, "engine": "gemini"}

    async def _generate_with_audio(self, audio_bytes: bytes, prompt: str) -> str:
        """One generateContent call with inline WAV audio + a text prompt."""
        b64 = base64.b64encode(audio_bytes).decode()
        model = self.settings.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "audio/wav", "data": b64}},
        ]}],
            "generationConfig": {"maxOutputTokens": 8192,
                                 "responseMimeType": "application/json"}}
        last_exc: Exception | None = None
        for _ in range(len(self._keys)):
            key = self._next_key()
            try:
                async with self._client() as client:
                    resp = await client.post(url, params={"key": key}, json=body)
                if resp.status_code != 200:
                    if self._looks_like_quota(resp.text, resp.status_code):
                        self._rotate()
                        last_exc = ProviderError(resp.text[:300], status=resp.status_code,
                                                 retryable=True)
                        continue
                    raise ProviderError(f"gemini transcription HTTP {resp.status_code}: {resp.text[:300]}",
                                        status=resp.status_code)
                data = resp.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if not text:
                    raise ProviderError("gemini transcription returned empty response")
                return text
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_exc = exc
                self._rotate()
        raise ProviderError(f"gemini transcription: all {len(self._keys)} keys exhausted: {last_exc}")

    async def health_check(self) -> tuple[bool, int | None, str | None]:
        if not self.configured:
            return False, None, "unconfigured"
        started = time.monotonic()
        try:
            async with self._client() as client:
                # Check the CONFIGURED model itself, not the model list:
                # listing models returned 200 while gemini-2.0-flash was
                # already retired, so health lied ("healthy") while every
                # real call 404'd (live 2026-10-17).
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.settings.GEMINI_MODEL}",
                    params={"key": self._next_key()},
                    timeout=15,
                )
            ms = int((time.monotonic() - started) * 1000)
            if resp.status_code == 200:
                return True, ms, None
            return False, ms, f"HTTP {resp.status_code}"
        except Exception as exc:
            return False, None, str(exc)[:200]


# ------------------------------------------------- OpenAI-compatible base
class _OpenAICompatProvider(AIProvider):
    """Shared logic for Groq / OpenRouter (OpenAI chat-completions API)."""

    api_base: str = ""
    default_model: str = ""
    extra_headers: dict[str, str] = {}

    def _keys(self) -> list[str]:
        raise NotImplementedError

    @property
    def configured(self) -> bool:
        return bool(self._keys())

    async def generate_text(self, prompt: str, *, model: str | None = None,
                            json_mode: bool = False, max_tokens: int = 2048) -> str:
        keys = self._keys()
        if not keys:
            raise ProviderError(f"{self.name} not configured (no API key)")
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last_exc: Exception | None = None
        for key in keys:
            headers = {"Authorization": f"Bearer {key}", **self.extra_headers}
            try:
                async with self._client() as client:
                    resp = await client.post(f"{self.api_base}/chat/completions",
                                             headers=headers, json=payload)
                if resp.status_code != 200:
                    if self._looks_like_quota(resp.text, resp.status_code):
                        log.warning("%s key exhausted (%s); trying next",
                                    self.name, resp.status_code)
                        last_exc = ProviderError(resp.text[:300], status=resp.status_code,
                                                 retryable=True)
                        continue
                    raise ProviderError(f"{self.name} HTTP {resp.status_code}: {resp.text[:300]}",
                                        status=resp.status_code)
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                if not text:
                    raise ProviderError(f"{self.name} returned empty response")
                return text
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_exc = exc
        raise ProviderError(f"{self.name}: all keys failed: {last_exc}")

    async def health_check(self) -> tuple[bool, int | None, str | None]:
        keys = self._keys()
        if not keys:
            return False, None, "unconfigured"
        started = time.monotonic()
        try:
            async with self._client() as client:
                resp = await client.get(
                    f"{self.api_base}/models",
                    headers={"Authorization": f"Bearer {keys[0]}"},
                    timeout=15,
                )
            ms = int((time.monotonic() - started) * 1000)
            return (True, ms, None) if resp.status_code == 200 else (False, ms, f"HTTP {resp.status_code}")
        except Exception as exc:
            return False, None, str(exc)[:200]


class GroqProvider(_OpenAICompatProvider):
    name = "groq"
    api_base = "https://api.groq.com/openai/v1"

    def __init__(self, settings, transport=None, keys: list[str] | None = None):
        super().__init__(settings, transport)
        # keys override: a per-user (BYOK) key for one job. When None, the
        # server env keys are used (settings.groq_keys).
        self._override_keys: list[str] | None = list(keys) if keys is not None else None
        self.default_model = settings.GROQ_MODEL

    def _keys(self) -> list[str]:
        return self._override_keys if self._override_keys is not None else self.settings.groq_keys

    async def transcribe(self, audio_path: str | Path) -> dict:
        keys = self._keys()
        if not keys:
            raise ProviderError("groq not configured (no API key)")
        last_exc: Exception | None = None
        for key in keys:
            try:
                async with self._client() as client:
                    with open(audio_path, "rb") as fh:
                        resp = await client.post(
                            f"{self.api_base}/audio/transcriptions",
                            headers={"Authorization": f"Bearer {key}"},
                            files={"file": (Path(audio_path).name, fh, "audio/wav")},
                            data={"model": "whisper-large-v3-turbo",
                                  "response_format": "verbose_json",
                                  "timestamp_granularities[]": "segment"},
                            timeout=300,
                        )
                if resp.status_code != 200:
                    if self._looks_like_quota(resp.text, resp.status_code):
                        last_exc = ProviderError(resp.text[:200], status=resp.status_code,
                                                 retryable=True)
                        continue
                    raise ProviderError(f"groq transcription HTTP {resp.status_code}")
                data = resp.json()
                segments = [
                    {"start": float(s.get("start", 0)), "end": float(s.get("end", 0)),
                     "text": s.get("text", "").strip()}
                    for s in data.get("segments", [])
                ]
                return {"transcript": segments, "language": data.get("language"),
                        "confidence": None, "engine": "groq-whisper"}
            except ProviderError:
                raise
            except (httpx.HTTPError, OSError, ValueError) as exc:
                last_exc = exc
        raise ProviderError(f"groq transcription failed: {last_exc}")


class OpenRouterProvider(_OpenAICompatProvider):
    name = "openrouter"
    api_base = "https://openrouter.ai/api/v1"
    extra_headers = {
        "HTTP-Referer": "https://ai-video-recap-platform",
        "X-Title": "AI Video Recap Platform",
    }

    def __init__(self, settings, transport=None):
        super().__init__(settings, transport)
        self.default_model = settings.OPENROUTER_MODEL

    def _keys(self) -> list[str]:
        return self.settings.openrouter_keys


# ------------------------------------------------------- Hugging Face
class HuggingFaceProvider(AIProvider):
    name = "huggingface"

    @property
    def configured(self) -> bool:
        return bool(self.settings.HF_TOKEN)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.HF_TOKEN}"}

    async def generate_text(self, prompt: str, *, model: str | None = None,
                            json_mode: bool = False, max_tokens: int = 2048) -> str:
        # HF text fallback: use a small instruct model via the chat API.
        if not self.configured:
            raise ProviderError("huggingface not configured (no token)")
        model = model or "HuggingFaceH4/zephyr-7b-beta"
        url = f"https://api-inference.huggingface.co/models/{model}"
        try:
            async with self._client() as client:
                resp = await client.post(
                    url, headers=self._headers(),
                    json={"inputs": prompt,
                          "parameters": {"max_new_tokens": max_tokens,
                                         "return_full_text": False}},
                    timeout=180,
                )
            if resp.status_code != 200:
                raise ProviderError(f"huggingface HTTP {resp.status_code}: {resp.text[:200]}",
                                    status=resp.status_code,
                                    retryable=resp.status_code in RETRYABLE_KEY_ERRORS)
            data = resp.json()
            if isinstance(data, list) and data:
                return str(data[0].get("generated_text", "")).strip()
            return str(data).strip()
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"huggingface error: {exc}") from exc

    async def analyze_image(self, image_path: str | Path, prompt: str) -> dict:
        if not self.configured:
            raise ProviderError("huggingface not configured (no token)")
        raw = Path(image_path).read_bytes()
        last_exc: Exception | None = None
        for model in self.settings.hf_vision_model_list:
            url = f"https://api-inference.huggingface.co/models/{model}"
            try:
                async with self._client() as client:
                    resp = await client.post(
                        url, headers={**self._headers(), "Content-Type": "image/jpeg"},
                        content=raw, timeout=180,
                    )
                if resp.status_code != 200:
                    last_exc = ProviderError(f"{model}: HTTP {resp.status_code}",
                                             status=resp.status_code,
                                             retryable=resp.status_code in RETRYABLE_KEY_ERRORS)
                    continue
                data = resp.json()
                text = data[0].get("generated_text", "") if isinstance(data, list) and data else str(data)
                return {"description": str(text).strip(), "model": model}
            except ProviderError as exc:
                last_exc = exc
            except httpx.HTTPError as exc:
                last_exc = ProviderError(str(exc))
        raise ProviderError(f"huggingface vision failed on all models: {last_exc}")

    async def health_check(self) -> tuple[bool, int | None, str | None]:
        if not self.configured:
            return False, None, "unconfigured"
        started = time.monotonic()
        try:
            async with self._client() as client:
                resp = await client.get("https://huggingface.co/api/whoami-v2",
                                        headers=self._headers(), timeout=15)
            ms = int((time.monotonic() - started) * 1000)
            return (True, ms, None) if resp.status_code == 200 else (False, ms, f"HTTP {resp.status_code}")
        except Exception as exc:
            return False, None, str(exc)[:200]


# ---------------------------------------------------------------- Manager
class ProviderManager:
    """Routes AI tasks across providers with key rotation + fallback chain."""

    def __init__(self, settings: Settings | None = None,
                 transports: dict[str, httpx.BaseTransport] | None = None):
        self.settings = settings or get_settings()
        transports = transports or {}
        self.providers: dict[str, AIProvider] = {
            "gemini": GeminiProvider(self.settings, transports.get("gemini")),
            "groq": GroqProvider(self.settings, transports.get("groq")),
            "openrouter": OpenRouterProvider(self.settings, transports.get("openrouter")),
            "huggingface": HuggingFaceProvider(self.settings, transports.get("huggingface")),
        }

    # -- usage logging (best effort; never raises) -------------------------
    def _log_usage(self, provider: str, model: str | None, task: str,
                   success: bool, latency_ms: int | None,
                   user_id: str | None = None, job_id: str | None = None,
                   error: str | None = None) -> None:
        try:
            from backend.database import ApiUsage, get_session_factory  # noqa: PLC0415
            db = get_session_factory()()
            try:
                db.add(ApiUsage(user_id=user_id, job_id=job_id, provider=provider,
                                model=model, task=task, success=success,
                                latency_ms=latency_ms, error=(error or "")[:2000] or None))
                db.commit()
            finally:
                db.close()
        except Exception as exc:  # logging must never break the pipeline
            log.warning("ApiUsage log failed: %s", exc)

    # -- text completion with fallback chain --------------------------------
    async def complete(self, task: str, prompt: str, *,
                       json_mode: bool = False, max_tokens: int = 2048,
                       user_id: str | None = None, job_id: str | None = None,
                       models: dict[str, str] | None = None) -> tuple[str, str]:
        """
        Run a text task through the provider chain.
        Returns (text, provider_name). Raises ProviderError if all fail.
        """
        chain = TASK_ROUTES.get(task, TASK_ROUTES["backup"])
        errors: list[str] = []
        for provider_name in chain:
            provider = self.providers[provider_name]
            model = (models or {}).get(provider_name)
            for attempt in (1, 2):  # one retry per provider, then switch
                started = time.monotonic()
                try:
                    text = await provider.generate_text(
                        prompt, model=model, json_mode=json_mode, max_tokens=max_tokens)
                    ms = int((time.monotonic() - started) * 1000)
                    self._log_usage(provider_name, model, task, True, ms, user_id, job_id)
                    log.info("task=%s provider=%s ok (%d ms)", task, provider_name, ms)
                    return text, provider_name
                except ProviderError as exc:
                    ms = int((time.monotonic() - started) * 1000)
                    self._log_usage(provider_name, model, task, False, ms, user_id, job_id,
                                    str(exc))
                    errors.append(f"{provider_name}: {exc}")
                    log.warning("task=%s provider=%s attempt=%d failed: %s",
                                task, provider_name, attempt, exc)
                    if attempt == 1 and exc.retryable:
                        await asyncio.sleep(1.5 * attempt)
                        continue
                    break  # switch provider
        raise ProviderError(f"all providers failed for task={task}: {' | '.join(errors)}")

    # -- speech -------------------------------------------------------------
    async def transcribe(self, audio_path: str | Path, *,
                         user_id: str | None = None,
                         job_id: str | None = None) -> tuple[dict, str]:
        """Speech task chain: groq -> huggingface. Returns (result, provider)."""
        errors: list[str] = []
        for provider_name in TASK_ROUTES["speech"]:
            provider = self.providers[provider_name]
            started = time.monotonic()
            try:
                result = await provider.transcribe(audio_path)
                ms = int((time.monotonic() - started) * 1000)
                self._log_usage(provider_name, None, "speech", True, ms, user_id, job_id)
                return result, provider_name
            except ProviderError as exc:
                ms = int((time.monotonic() - started) * 1000)
                self._log_usage(provider_name, None, "speech", False, ms, user_id, job_id, str(exc))
                errors.append(f"{provider_name}: {exc}")
        raise ProviderError(f"all speech providers failed: {' | '.join(errors)}")

    async def transcribe_with(self, provider_name: str, audio_path: str | Path, *,
                              key: str | None = None) -> tuple[dict, str]:
        """Transcribe with ONE named provider (user's choice), not the chain.

        When key is given, the provider runs with that per-user (BYOK) key
        instead of the server env keys. Raises ProviderError on failure.
        """
        provider_cls = {"gemini": GeminiProvider, "groq": GroqProvider}.get(provider_name)
        if provider_cls is None:
            raise ProviderError(f"unknown transcription provider: {provider_name}")
        provider = provider_cls(self.settings, keys=[key] if key else None)
        result = await provider.transcribe(audio_path)
        return result, provider_name

    # -- vision -------------------------------------------------------------
    async def describe_frame(self, image_path: str | Path, prompt: str, *,
                             user_id: str | None = None,
                             job_id: str | None = None) -> tuple[dict, str]:
        """Vision task chain: huggingface -> gemini -> openrouter."""
        errors: list[str] = []
        for provider_name in TASK_ROUTES["vision"]:
            provider = self.providers[provider_name]
            started = time.monotonic()
            try:
                result = await provider.analyze_image(image_path, prompt)
                ms = int((time.monotonic() - started) * 1000)
                self._log_usage(provider_name, None, "vision", True, ms, user_id, job_id)
                return result, provider_name
            except ProviderError as exc:
                ms = int((time.monotonic() - started) * 1000)
                self._log_usage(provider_name, None, "vision", False, ms, user_id, job_id, str(exc))
                errors.append(f"{provider_name}: {exc}")
        raise ProviderError(f"all vision providers failed: {' | '.join(errors)}")

    # -- health -------------------------------------------------------------
    async def health_check_all(self) -> dict[str, dict]:
        """Check every provider; returns {name: {status, latency_ms, error}}."""
        results: dict[str, dict] = {}
        for name, provider in self.providers.items():
            try:
                healthy, latency_ms, error = await provider.health_check()
                status = "healthy" if healthy else ("unconfigured" if error == "unconfigured" else "unhealthy")
            except Exception as exc:
                healthy, latency_ms, error, status = False, None, str(exc)[:200], "unhealthy"
            results[name] = {"status": status, "latency_ms": latency_ms, "error": error}
        return results

    def persist_health(self, results: dict[str, dict]) -> None:
        """Write health results to ProviderHealth + compute error rates."""
        try:
            from datetime import datetime, timedelta, timezone  # noqa: PLC0415

            from backend.database import ApiUsage, ProviderHealth, get_session_factory  # noqa: PLC0415
            db = get_session_factory()()
            try:
                since = datetime.now(timezone.utc) - timedelta(hours=1)
                for name, res in results.items():
                    total = db.query(ApiUsage).filter(
                        ApiUsage.provider == name,
                        ApiUsage.created_at >= since,
                    ).count()
                    fails = db.query(ApiUsage).filter(
                        ApiUsage.provider == name, ApiUsage.created_at >= since,
                        ApiUsage.success.is_(False)).count()
                    error_rate = (fails / total) if total else 0.0
                    row = db.query(ProviderHealth).filter_by(provider=name).one_or_none()
                    if row is None:
                        row = ProviderHealth(provider=name)
                        db.add(row)
                    row.status = res["status"]
                    row.latency_ms = res["latency_ms"]
                    row.error_rate = error_rate
                    row.last_error = res["error"]
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            log.warning("persist_health failed: %s", exc)


__all__ = [
    "AIProvider",
    "ProviderManager",
    "ProviderError",
    "TASK_ROUTES",
    "GeminiProvider",
    "GroqProvider",
    "OpenRouterProvider",
    "HuggingFaceProvider",
]
