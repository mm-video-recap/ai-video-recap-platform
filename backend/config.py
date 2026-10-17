"""
Central configuration for the AI Video Recap Platform backend.

All secrets come from environment variables only. Nothing is hardcoded.
See ../../.env.example (repo root) for the full list.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.security.jwt import normalize_supabase_url


def _collect_numbered_keys(prefix: str) -> list[str]:
    """Collect numbered env vars plus the bare KEY.

    Accepts BOTH naming styles, because owners naturally write either:
    zero-padded with underscore (GEMINI_API_KEY_01) and bare suffix
    (GEMINI_API_KEY2). Order: bare key first, then numbered in order.
    Duplicates are removed, order preserved.
    """
    keys: list[str] = []
    bare = os.environ.get(prefix)
    if bare:
        keys.append(bare)
    for i in range(1, 100):
        for name in (f"{prefix}_{i:02d}", f"{prefix}{i}"):
            value = os.environ.get(name)
            if value and value not in keys:
                keys.append(value)
    return keys


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "AI Video Recap Platform"
    APP_VERSION: str = "0.1.0"
    ENV: str = "development"
    API_BASE_URL: str = "http://localhost:8000"

    # --- Dev-only auth bypass (tests/local dev ONLY; default OFF) ---
    # When ENV=development and DEV_AUTH_BYPASS=1, the API accepts
    #   Authorization: Bearer dev-token-<user-id>
    # as the user <user-id> (email <user-id>@dev.local unless it already
    # contains "@"). NEVER enable in production.
    DEV_AUTH_BYPASS: bool = False

    # --- Admin users (comma-separated emails; matches Supabase JWT email) ---
    ADMIN_EMAILS: str = ""

    # --- Owner account (ONE email). Only this account may use the
    # server (env) AI keys. Everyone else MUST bring both their own
    # Gemini + Groq keys — the upload endpoint enforces it. Set this
    # to the owner's login email on the hosting provider.
    OWNER_EMAIL: str = ""

    # --- Service token (machine-to-machine, e.g. n8n monitoring flow) ---
    # When set, Authorization: Bearer <RECAP_API_SERVICE_TOKEN> authenticates
    # as the service identity "service:n8n" (admin). The n8n monitoring flow
    # uses this for GET /api/admin/overview + /api/admin/providers.
    # Generate with: openssl rand -hex 32. Empty = disabled.
    RECAP_API_SERVICE_TOKEN: str = ""

    # --- Supabase ---
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""          # anon/service key (server-side only)
    SUPABASE_JWT_SECRET: str = ""   # HS256 secret; if empty, JWKS (RS256) is used
    SUPABASE_ANON_KEY: str = ""

    # --- Database (Supabase free PostgreSQL; sqlite fallback for dev/tests) ---
    DATABASE_URL: str = ""

    # --- Storage (local fallback mirrors the /uploads /processing /results layout) ---
    STORAGE_PROVIDER: str = "local"  # local | r2 | supabase
    # STORAGE_ROOT = <repo root>/storage. In Docker the backend lives at
    # /app/backend, so this resolves to /app/storage (matches docker-compose
    # mounts). Override via STORAGE_ROOT env when needed.
    STORAGE_ROOT: str = str(Path(__file__).resolve().parent.parent / "storage")
    SUPABASE_STORAGE_BUCKET: str = "recap-results"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_UPLOADS: str = "recap-uploads"
    R2_BUCKET_RESULTS: str = "recap-results"
    R2_BUCKET_TEMP: str = "recap-temporary"
    UPLOAD_CHUNK_SIZE: int = 2 * 1024 * 1024  # 2 MiB
    MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB free-tier cap
    MAX_VIDEO_DURATION_SEC: int = 1800  # 30 min free-tier cap

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False  # dev/test escape hatch (no broker needed)
    CELERY_TASK_TIME_LIMIT_SEC: int = 3600  # hard kill per task
    CELERY_TASK_SOFT_TIME_LIMIT_SEC: int = 3300

    # --- AI providers (keys live ONLY in env; never in code) ---
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    # Groq free-tier vision model (researched 2026-10-17; Groq retires
    # vision models without notice — override via env, do NOT hard-code
    # a new default without checking Groq's rate-limit page).
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    HF_TOKEN: str = ""
    HF_VISION_MODELS: str = "llava-hf/llava-1.5-7b-hf,Qwen/Qwen2-VL-7B-Instruct,openbmb/MiniCPM-V-2_6"
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    PROVIDER_HEALTH_CHECK_SECONDS: int = 300  # 5 minutes per spec

    # --- Email (OAuth2 only; NEVER passwords) ---
    EMAIL_PROVIDER: str = "gmail"  # gmail | msgraph | none
    EMAIL_ENABLED: bool = False  # master switch; False => log-only no-op
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    GMAIL_SENDER: str = ""
    MSGRAPH_TENANT_ID: str = ""
    MSGRAPH_CLIENT_ID: str = ""
    MSGRAPH_CLIENT_SECRET: str = ""
    MSGRAPH_SENDER: str = ""

    # --- Fair-use limits (free tier) ---
    MAX_UPLOADS_PER_DAY: int = 5
    MAX_PROCESSING_MINUTES_PER_DAY: int = 60
    MAX_AI_REQUESTS_PER_DAY: int = 100

    # --- Rate limiting ---
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    # --- CORS ---
    # EXACT origins only — wildcards are REJECTED at startup (see
    # backend/main.py build_cors_options). A wildcard origin combined with
    # allow_credentials=True would let ANY matching subdomain (e.g. any
    # *.pages.dev site) make credentialed API requests. Production must
    # list the exact deployed frontend origin(s) here, e.g.
    # CORS_ORIGINS=https://myan-recap.pages.dev
    # Default is localhost dev origins only.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Whisper ---
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"

    # --- Community workers ---
    WORKER_GATEWAY_TOKEN: str = ""

    # --- Output language for summaries (en | my); user-selectable per request ---
    DEFAULT_OUTPUT_LANG: str = "en"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    def is_owner(self, email: str | None) -> bool:
        """True only for the single owner account (OWNER_EMAIL)."""
        return bool(self.OWNER_EMAIL and email
                    and email.strip().lower() == self.OWNER_EMAIL.strip().lower())

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _split_origins(cls, v: str) -> list[str]:
        return [o.strip() for o in v.split(",") if o.strip()]

    @field_validator("SUPABASE_URL")
    @classmethod
    def _normalize_supabase_url(cls, v: str) -> str:
        # Accept a pasted Supabase API URL (.../rest/v1, .../auth/v1, ...)
        # and reduce it to the bare project URL every consumer expects.
        # See normalize_supabase_url (live incident 2026-10-16).
        return normalize_supabase_url(v)

    @property
    def gemini_keys(self) -> list[str]:
        return _collect_numbered_keys("GEMINI_API_KEY") + _collect_numbered_keys("GEMINI_KEY")

    @property
    def groq_keys(self) -> list[str]:
        return _collect_numbered_keys("GROQ_API_KEY") + _collect_numbered_keys("GROQ_KEY")

    @property
    def openrouter_keys(self) -> list[str]:
        return _collect_numbered_keys("OPENROUTER_API_KEY") + _collect_numbered_keys("OPENROUTER_KEY")

    @property
    def hf_vision_model_list(self) -> list[str]:
        return [m.strip() for m in self.HF_VISION_MODELS.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
