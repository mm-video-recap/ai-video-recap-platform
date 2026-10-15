# SECURITY — Autonomous AI Video Recap Platform

## Authentication & authorization

- **Supabase JWT Bearer** on all `/api/*` except `GET /health`, `GET /api/health`, and worker routes (see below). The backend **verifies** tokens; it never issues them — there is no backend register/login (`GET /api/auth/me` only). Feedback/report endpoints also require auth (`get_current_user`) — they are NOT optional-auth.
- **Row Level Security (RLS)** on all 13 user/service tables in Supabase (`supabase/migrations/001_init.sql`): users can read/update only their own row (no INSERT policy — the backend creates rows via service_role); videos/jobs/feedback/bug_reports/feature_requests owner-only; outputs/email_records via the parent job's owner. `api_usage`, `provider_health`, `community_workers`, `error_log`, `analytics_events` have RLS enabled with **no** policies (anon key gets no access). The backend uses the `service_role` key **server-side only** and enforces ownership in code as well (defense in depth).
- **Admin endpoints** (`/api/admin/*`) require admin. Admin comes from: Supabase JWT `app_metadata.is_admin`, a `service_role`/`admin` JWT role, or the `ADMIN_EMAILS` env list (synced onto the `users.is_admin` column on each request).
- **Service token:** `RECAP_API_SERVICE_TOKEN` (env) authenticates the n8n monitoring flow as the service identity `service:n8n` (admin). Empty = disabled. Never log it.
- **Dev bypass:** `ENV=development` + `DEV_AUTH_BYPASS=1` accepts `Bearer dev-token-<user-id>`. Default OFF — never enable in production.
- **Community workers** authenticate with the shared `X-Worker-Token` gateway token (`WORKER_GATEWAY_TOKEN` env) — never with user JWTs. Workers receive only opaque job ids and media paths, no PII. Note the token is **shared, not per-worker**: rotation/revocation affects all workers at once.

## Secrets handling (env-only)

- All secrets live in environment variables / the cloud provider's secret manager. **Never in code, tests, docs, logs, or commit messages.**
- `.env.example` contains **placeholders only**; CI runs `scripts/secret_scan.py` on every push and fails on hits.
- The frontend (`NEXT_PUBLIC_*`) exposes only the Supabase **anon** key and public URLs — never the service role key.
- AI provider keys are system-owner managed; users never supply keys, and keys never travel to the browser.

## Upload validation & fair use

- **Validation:** magic-byte sniffing + container check (mp4/mov/webm/mkv) + ffprobe metadata; rejected files return **400** (not 422). Uploads are streamed to a temp file in 4 MiB chunks and the temp file is always deleted.
- **Caps (env-configurable, enforced in `check_fair_use`):** `MAX_UPLOAD_BYTES` (2 GiB), `MAX_VIDEO_DURATION_SEC` (1800 s), `MAX_UPLOADS_PER_DAY` (5), `MAX_PROCESSING_MINUTES_PER_DAY` (60), `MAX_AI_REQUESTS_PER_DAY` (100) per user.
- **Rate limiting:** slowapi, **per-IP only** (`get_remote_address`): default `RATE_LIMIT_DEFAULT` (120/minute) + `10/minute` on `POST /api/videos/upload`. There is **no** per-user limiter and no `Retry-After` header on the 429 handler.
- **Hash stored, dedup NOT enforced:** ingestion stores a `sha256_prefix` (full SHA-256 of the first 64 MiB) on the video row, but nothing checks it before insert — the same file can be uploaded twice.
- **Abuse protection:** `temporary/` artifact expiry via the daily Celery cleanup task (requires Beat running), admin error dashboard. No executable/macro-specific rejection beyond the container magic-byte check.

## Transport & platform

- **HTTPS everywhere** in production; SSE `?token=` auth requires HTTPS (tokens in URLs must not travel over plaintext). Note: JWTs in query strings can also land in server/proxy access logs — prefer header auth where possible.
- **CORS:** `allow_credentials=True` with **exact origins only** — `backend/main.py build_cors_options()` REJECTS any wildcard origin at startup (raises ValueError), and no `allow_origin_regex` is used. Default `CORS_ORIGINS` is localhost dev origins only; production must list the exact deployed frontend origin(s), e.g. `CORS_ORIGINS=https://myan-recap.pages.dev`. (Fixed 2026-10-15 deploy pass: the previous `https://*.pages.dev` wildcard + credentials combination is gone.)
- **Email is OAuth2-only** (Gmail / Microsoft Graph). No SMTP passwords are stored, ever; when email is unconfigured the notifier is a graceful no-op.
- **Dependencies:** pinned in `backend/requirements.txt` (`==`) and `frontend/package-lock.json`. ⚠️ CI does **not** currently run `pip audit` / `npm audit` (`.github/workflows/ci.yml` has backend tests, frontend build, secret scan, compose validation only) — add audit jobs before launch. In this sandbox `npm audit` could not run (registry policy denied the audit endpoint) and `pip-audit` is not installed, so no audit result exists yet.
- **Local storage path traversal:** `LocalStorage._resolve` confines keys under `STORAGE_ROOT`. Download (`GET /api/results/{job_id}/download`) serves only rows the caller owns, via the stored `storage_path`.
- **Debug flags:** `ENV=development` triggers `create_all()` on startup (auto-create tables) — production must set `ENV=production`. `DEV_AUTH_BYPASS` must be `0` in production.

## Data & privacy

- Videos/results are private to the owner (signed URLs or auth-gated); R2/Supabase buckets are private by default.
- Deleting a video deletes its jobs, results, artifacts, and stored files.
- Analytics events carry UUIDs, never emails or raw content. AI-memory preferences are per-user, RLS-protected, deleted with the account, and opt-out in `/settings`.
- Public legal pages: `/privacy`, `/terms`, `/content-policy`, `/dmca`, `/contact`.

## Reporting a vulnerability

**Do not open a public issue, and do not post exploit details publicly.** No private email contact is published yet. Once this repository is public on GitHub, report vulnerabilities via GitHub **private vulnerability reporting** (to be enabled when the repo is created). We aim to acknowledge within 72 hours and will coordinate disclosure.
