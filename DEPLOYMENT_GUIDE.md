# DEPLOYMENT GUIDE — Autonomous AI Video Recap Platform

> **Canonical copy.** This file at the project root is the single maintained deployment guide.
> `docs/DEPLOYMENT_GUIDE.md` is only a pointer to this file. Do not maintain two copies.
> Last verified/corrected: 2026-10-15 00:37 Asia/Yangon (deployment pass — Phase 7). Prior version: 2026-10-14 completion pass.

**How to read this guide:** every step is a ☐ **user-action checklist item**. Nothing here is executed automatically — you (the system owner) perform each step in the provider's dashboard/CLI. Check items off as you go.

Target production topology (all free tiers — demo-grade, see limits below):

- **Frontend** → Cloudflare Pages (from GitHub) — static export, `https://<project>.pages.dev`
- **Backend API** → Render free Docker **web service** — `https://<service>.onrender.com`
- **Worker + Beat** → Render free Docker **WEB service** (free has no background-worker type) — Celery worker + tiny HTTP health listener + embedded Beat (`celery worker -B`)
- **Redis** → Upstash free (`rediss://` TLS) — **set a budget cap** (overages bill)
- **File storage** → Cloudflare R2 (free egress) — `STORAGE_PROVIDER=r2`, buckets `recap-uploads` / `recap-results` / `recap-temporary`, ALL PRIVATE
- **Database/Auth** → Supabase free (Singapore, ap-southeast-1) — migration run exactly ONCE
- **Automation** → n8n (self-hosted or n8n Cloud free)

**⚠️ $0 free-tier limits (demo-grade only):** Render free services sleep after ~15 min idle; first request after sleep takes 30–60s+; 750 free instance-hours/month/workspace shared (forced-keep-awake can suspend the workspace); jobs process only while the worker is awake; embedded Beat (`-B`) dies if the worker restarts (acceptable for demo, NOT for the paid fallback — use a separate Beat there). **Paid fallback if always-on is wanted (≈ $7–14/mo):** Render Starter API web (~$7/mo) + background worker with worker+Beat combined (~$7/mo) + Upstash/Supabase/Pages/R2 free. Single-service alternative: one Starter service running API+worker+beat under supervisor (~$7/mo, single point of failure). $0 self-hosted alternative: Oracle Cloud Always Free VM (Ampere A1, 2 OCPU/12 GB, card for identity verification only) running the full docker-compose stack. **Never enter payment details without the owner's approval.** Free-tier figures are from Oct 2026 web sources — re-verify each provider's pricing page at deploy time.

Prerequisites: a GitHub account, an email address for OAuth consent (Gmail or Microsoft), and the repo pushed to GitHub.

---

## ⚠️ PRE-LAUNCH MANDATORY FIXES

- ✅ **FIX 1 — CORS wildcard + credentials (HIGHEST infra risk) — FIXED 2026-10-15 deploy pass.** `backend/main.py` now builds CORS from an exact-origin allowlist only (`build_cors_options()`): any wildcard in `CORS_ORIGINS` raises ValueError at startup, and no `allow_origin_regex` is passed to CORSMiddleware. Default `CORS_ORIGINS` is localhost dev origins only. **Operator action at deploy time:** set the exact production frontend origin(s) in `CORS_ORIGINS` (e.g. `https://<your-project>.pages.dev`). Re-verify with an OPTIONS preflight from a non-listed origin (must NOT return the credentialed allow-origin) — covered by the backend regression test `test_cors_rejects_wildcard_and_unlisted_origin`.
- ☐ **FIX 2 — Frontend static export (was: Pages adapter).** `frontend/next.config.mjs` is still an empty `{}`. The frontend needs **NO server-side Next.js** (verified 2026-10-15: all 15 routes are `"use client"`; zero `route.ts`, middleware, Server Actions, `getServerSideProps`/`getStaticProps`, `next/image`, `next/headers`; data via browser fetch). So the correct path is **static export**, NOT an adapter: in `frontend/next.config.mjs` set `output: 'export'` + `images: { unoptimized: true }` (if `next/image` is ever added), and add `generateStaticParams()` stubs returning `[]` for `processing/[jobId]` + `result/[jobId]`. ⚠️ `@cloudflare/next-on-pages` is **DEPRECATED** — do not use it. Alternative: deploy the frontend as a Node service (e.g. Render Web Service running `npm run build && npm start` from `frontend/`, or Vercel). Pages build output directory after the static-export change: `out/`.
- ☐ **FIX 3 — `NEXT_PUBLIC_API_URL` must be set in the frontend host env BEFORE the Pages build.** The frontend falls back to `http://localhost:8000` (see `frontend/lib/api.ts`) when this is unset. That fallback is intentional for local dev but **must** be overridden in production, or the deployed frontend will call localhost. `NEXT_PUBLIC_*` values are baked at build time — changing them needs a rebuild/redeploy.
- ☐ **FIX 4 — Separate persistent worker + Redis + Beat are MANDATORY.** The API only enqueues jobs. Without a running Celery worker, Redis broker, and Celery Beat process, uploads stay `queued` forever. Do not deploy the API alone and expect processing to work. On Render free, the worker runs as a **WEB service** with a tiny HTTP health listener + embedded Beat (see Step 4, Option B).
- ☐ **FIX 5 — `docker compose up` needs a real `.env`.** Compose uses `env_file`; without a filled-in `.env` (copied from `.env.example`) the stack fails to start. Never commit the real `.env`.
- ✅ **FIX 6 — `subtitle_language` + `recap_style` — FIXED 2026-10-15 (was: DECISION NEEDED).** The backend now accepts them as validated query params (`my|en|none`, `concise|detailed|highlights`), persists them on `Job`, and exposes them in `JobStatus`; the frontend sends them. No UI change needed.
- ✅ **FIX 7 — Upload size gate — FIXED 2026-10-15 (was: NOTE / open item).** The upload route now checks `Content-Length` early (`Content-Length` > cap → **413** before any body read) and aborts chunked bodies mid-stream, deleting the partial temp file. A real 2 GB HTTP upload was still never attempted (unit-level test only) — the streaming-count branch is code-reviewed only.
- ☐ **FIX 8 — Render `$PORT` binding (NEW — do before first Render deploy).** Change the backend Dockerfile CMD to `sh -c "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"`. Render assigns the port via `$PORT`; a hardcoded 8000 will fail the health check.
- ☐ **FIX 9 — Worker-as-web-service health listener (NEW — do before first Render worker deploy).** Add a tiny HTTP health listener (e.g. Python `http.server` on `$PORT`, 200 on `/health`) alongside the worker, and run the worker with embedded Beat: `celery -A backend.celery_app.celery worker -B -Q video_upload_queue,video_processing_queue,ai_analysis_queue,render_queue,email_queue --loglevel=info`. Caveat: `-B` Beat dies if the worker restarts — demo-acceptable, not for the paid fallback (run a separate Beat there).
- ☐ **NOTE — `DEV_AUTH_BYPASS` must stay `0` in production** and `ENV=production` (in development, `ENV=development` auto-creates tables via `create_all` — production must use the migration instead).

## Deployment status (honest — 2026-10-15)

**Nothing is deployed.** There is no staging or production environment, no live URL, no Supabase project, no Redis instance, no Docker image build (Docker was not available in the verification environment), and no real AI recap has ever been produced (no API key). Do not treat any URL in this guide as a live deployment — `https://<your-service>.onrender.com`, `https://recap.example.com`, `https://api.example.com` are placeholders for YOUR domains.

---

## Step 0 — Prepare the repository

- ☐ Push the repo to GitHub (**public vs private — your choice, needs your approval**). Note: the working copy has no `.git` yet — the user creates the repo via browser takeover, then run `git init`, `git add -A`, verify `git status` shows no `.env`, run `python3 scripts/secret_scan.py` (exit 0), commit, `git remote add`, push. A full-tree push cannot be done via the GitHub web UI — local git auth is needed.
- ☐ Copy `.env.example` to `.env` locally and fill in real values **only on your machine** (never commit `.env`; it is git-ignored).
- ☐ Confirm `scripts/secret_scan.py` passes: `python3 scripts/secret_scan.py` (exit 0, no hits).

## Step 1 — Supabase (database + auth + optional storage)

- ☐ Go to https://supabase.com → **New project** (free plan). **REGION: Singapore (ap-southeast-1) — cannot change after creation.** Suggested name: `ai-video-recap`. Save the project URL and the `anon` + `service_role` keys — into host secret settings later, never into chat/code.
- ☐ In **Authentication → Providers**, enable **Email** (the frontend uses email+password) and **Google** (the frontend's "Continue with Google" button needs the Google provider enabled + a Google Cloud OAuth client ID + Secret).
- ☐ In **Authentication → URL Configuration**, set Site URL = your frontend URL (e.g. `https://<your-project>.pages.dev`); add Redirect URLs = frontend URL + `https://<project>.pages.dev/**`. In the Google Cloud OAuth client, set the Authorized redirect URI = `https://<project-ref>.supabase.co/auth/v1/callback`.
- ☐ Open **SQL Editor** and paste the **ENTIRE** `supabase/migrations/001_init.sql` (the updated 2026-10-15 version — includes new columns + `size_bytes bigint`) and Run, **exactly ONCE**, against the fresh project. Current file: `001_init.sql` — 13 tables: `users`, `videos`, `jobs`, `outputs`, `api_usage`, `email_records`, `feedback`, `bug_reports`, `feature_requests`, `provider_health`, `community_workers`, `error_log`, `analytics_events`. (There is no `results` table — finished-video rows live in `outputs` with `kind='recap_video'`.)
  - ⚠️ The migration is **NOT idempotent** (plain `CREATE TABLE` / `CREATE POLICY`, no `IF NOT EXISTS`): run it exactly **once** against a fresh project. Never run it on a project that already has these tables/data without confirming. If it fails partway, inspect which statements applied; restore/reset rather than hand-dropping tables.
  - The migration creates **no Storage buckets and no `storage.objects` policies** — see the Storage bullet below. It also creates **no `auth.users` → `public.users` trigger**: the backend auto-creates the `public.users` row on the user's first authenticated API call (`backend/api/deps.py`), so no trigger is needed.
  - Migration validation note (2026-10-14 + 2026-10-15 re-check): the SQL was validated with a REAL Postgres parser (`pglast` v8.6) — 47 statements, zero syntax errors. That is parse-validation only, NOT execution against a DB. Known non-blocking notes: some indexes are missing in the migration vs. the models (performance-only); nullability is looser in SQL for feedback/bug_reports/feature_requests user fields + `provider_health.checked_at`; `feedback.rating` CHECK (1,2,3) exists in SQL only — fine; `size_bytes` is now `bigint` (fixed 2026-10-15).
- ☐ Confirm Row Level Security is enabled on all 13 tables (policies: users read/update only their own row; videos/jobs/feedback/bug_reports/feature_requests owner-only; outputs/email_records visible via the parent job's owner; api_usage/provider_health/community_workers/error_log/analytics_events have RLS on with **no** policies, so the anon key gets no access — service_role bypasses RLS for the backend).
- ☐ Get the pooled connection string from **Database** settings (port **6543**, `-pooler` host) for `DATABASE_URL` (backend only — never frontend).
- ☐ (Optional, if not using R2) In **Storage**, create ONE bucket: `recap-results` — **private**. That is the only bucket the app uses via `SUPABASE_STORAGE_BUCKET` (default `recap-results`); the backend reads/writes it with the service_role key and hands browsers short-lived signed URLs. Do NOT create `uploads`/`processing`/etc. buckets for Supabase — those names belong to the R2/local layouts. No storage policies are needed for backend-only access (service-role + signed URLs; the frontend never touches Storage; downloads go via `GET /api/results/{job_id}/download`).
- ☐ Supabase free tier (Oct 2026 — re-verify the pricing page): 500 MB DB, 1 GB storage, 5 GB egress, 50k MAU, 2 active projects, auto-pause after 7 days inactivity.

## Step 2 — Cloudflare R2 (file storage)

- ☐ Go to https://dash.cloudflare.com → **R2** → **Create bucket** (free tier). Create exactly these **3 buckets** (the app uses only these):
  - ☐ `recap-uploads` (original user uploads)
  - ☐ `recap-results` (finished recap MP4s + SRTs)
  - ☐ `recap-temporary` (intermediate agent artifacts, lifecycle-expire after 7 days)
  - **ALL THREE PRIVATE — no public access.** The backend hands browsers signed URLs. The guide's older `recap-processing` / `recap-thumbnails` buckets are unused by the app — optional, do not create them expecting traffic. (`.env.example`'s `R2_BUCKET_PROCESSING` / `R2_BUCKET_THUMBNAILS` are NOT read by `backend/config.py` — do not set them expecting effect.)
- ☐ In R2 → **Manage R2 API Tokens** → create a token with Object Read & Write **scoped to these 3 buckets only**; save **Account ID**, **Access Key ID**, **Secret Access Key** into the host secret settings.
- ☐ (Optional) Attach a custom domain to `recap-results` for direct download links, or keep signed URLs generated by the backend.
- ☐ Set `STORAGE_PROVIDER=r2` + `R2_BUCKET_UPLOADS` / `R2_BUCKET_RESULTS` / `R2_BUCKET_TEMP` on the backend + worker services.

## Step 3 — AI provider keys (system owner only)

Users never supply keys. Collect free-tier keys once, store them as secrets in the backend host (Step 4), never in the repo:

- ☐ **Gemini** — https://aistudio.google.com/app/apikey → create 1–4 keys (rotation pool: `GEMINI_API_KEY`, `GEMINI_KEY_01..03`).
- ☐ **Groq** — https://console.groq.com → free API key (`GROQ_API_KEY`).
- ☐ **OpenRouter** — https://openrouter.ai → free key (`OPENROUTER_API_KEY`).
- ☐ **Hugging Face** — https://huggingface.co/settings/tokens → read token (`HF_TOKEN`).

## Step 4 — Backend on Render (Docker)

### Option A — Hugging Face Spaces (Docker) — ⛔ DO NOT USE (STALE)

> **Correction (2026-10-15):** earlier versions of this guide listed HF Spaces (Docker) as a free backend option. Multiple Sept–Oct 2026 reports show Docker/Gradio/Streamlit **compute** Spaces now return **402 Payment Required (PRO ~$9/mo)**; only Static Spaces are free. **Do not use HF Spaces for the backend/worker.**

### Option B — Render (Docker) — recommended

Render is the recommended backend host. **Important free-tier facts:** Render free has **NO background-worker service type** — only web + static services. Free web services sleep after inactivity (cold start on the next request) and share 750 free instance-hours/month/workspace. The worker therefore runs as a second **WEB service** with a tiny HTTP health listener (Pre-launch FIX 9).

- ☐ **Redis first:** create a free Upstash Redis (Singapore, TLS) — see Step 4b. Do NOT use Render Key Value for the free path (Render free Key Value is in-memory/time-limited and unreliable). Copy the same Redis URL into **both** Render services as `REDIS_URL`, `CELERY_BROKER_URL` (same value, db 0), and `CELERY_RESULT_BACKEND` (same host, db 1). Set a **budget cap** in Upstash (overages bill).
- ☐ Go to https://dashboard.render.com → **New → Web Service** → connect the GitHub repo → **Docker** runtime, Dockerfile path `docker/Dockerfile.backend`, **Singapore** region, **Free** plan. Health-check path `/health` (also `/api/health`).
- ☐ Create a **second Web Service** (same repo, Docker) with `docker/Dockerfile.celery` (after FIX 9: health listener + embedded Beat), Singapore, Free, health-check `/health` on the dummy listener.
- ☐ In each service → **Environment**, add the **same full env set** from the env table below (both services need the identical secrets: DB, Supabase, R2, Redis/Celery, AI keys, `CORS_ORIGINS`, `ENV=production`, `DEV_AUTH_BYPASS=0`).
- ☐ Deploy; confirm `https://<your-service>.onrender.com/api/health` returns 200, and unauthenticated `GET /api/videos` → 401.
- ☐ Free-tier caveat: free web services sleep after inactivity (cold start on the next request) and free instances have limited RAM — CPU Whisper + FFmpeg renders are the heaviest load; test a real video before relying on the free tier. Jobs process only while the worker service is awake.

### Step 4b — Upstash Redis (free)

- ☐ Go to Upstash → create a free Redis database, **Singapore** region, TLS on. Copy the `rediss://` URL.
- ☐ Set `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` to the same host (db 1 on API + worker) on **both** Render services.
- ☐ Verify with `redis-cli PING` → `PONG` (or the provider's CLI). **Set a budget cap** — Upstash free is 500K commands/mo, 256 MB, 10 GB bandwidth, 10 DBs; overages bill.

### Local Docker (development / staging smoke test)

Docker was NOT available in the verification environment, so no image build has ever been attempted. On a Docker host:

- ☐ Copy `.env.example` to `.env` and fill in real values (compose reads it via `env_file`; without it `docker compose up` fails).
- ☐ `docker compose build` — then `docker compose config` to confirm the rendered config.
- ☐ `docker compose up` — verify: `GET /health` + `GET /api/health` return 200; `docker compose ps` shows all 5 services healthy (`redis`, `backend`, `celery`, `beat`, `frontend`).
- ☐ Prod commands inside the containers: backend `uvicorn backend.main:app --host 0.0.0.0 --port 8000`; celery worker on all 5 queues; frontend `npm start` port 3000 as non-root `nextjs`.

## Step 5 — Frontend on Cloudflare Pages

- ☐ First complete **Pre-launch FIX 2** (static export) — `next.config.mjs` must have `output: 'export'` before the first Pages deploy.
- ☐ Go to https://dash.cloudflare.com → **Pages** → **Create** → **Connect to Git** → select the repo.
- ☐ Build settings:
  - Build command: `npm run build`
  - Root directory: `frontend`
  - Output directory: `out/` (after the static-export change)
  - Build preset: **None / static** — NOT the Next.js SSR preset
- ☐ In Pages → **Settings → Environment variables**, add the `NEXT_PUBLIC_*` variables from the env table (these are public by design — anon key only, never the service role key): `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL=https://<render-api>.onrender.com` (**must be set BEFORE the build** — baked at build time; changing it needs a rebuild/redeploy), `NEXT_PUBLIC_DEFAULT_LOCALE=my`.
- ☐ Deploy; open the `*.pages.dev` URL and confirm the landing page renders in Burmese.
- ☐ Set the backend `CORS_ORIGINS` allowlist to exactly `https://<project>.pages.dev` (+ `http://localhost:3000` for local dev only). No wildcard.
- ☐ Log in via Supabase Auth and upload a test video end-to-end. Check the browser console for `localhost:8000` errors (means `NEXT_PUBLIC_API_URL` was not set at build time).
- ☐ Frontend/upload limits (verified to match the backend exactly): 2 GiB max, `mp4`/`mov`/`webm`/`mkv` only. The frontend has no 30-min duration cap — the backend rejects over-long videos with 400.

## Step 6 — Custom domain (optional)

- ☐ In Cloudflare → **Domains**, add your domain; in Pages → **Custom domains**, attach it (e.g. `recap.example.com`).
- ☐ Point the backend host's custom domain (Render supports it) to `api.example.com`; update `NEXT_PUBLIC_API_URL` in Pages env and redeploy.
- ☐ Add both domains to Supabase **Redirect URLs** and backend **CORS** origins (exact origins — see Pre-launch FIX 1; no wildcard with credentials).

## Step 7 — n8n automation (optional)

- ☐ Import each file in `n8n/` via n8n → **Workflows → Import from file**:
  - ☐ `email-notification-flow.json` (job-complete / job-failed emails)
  - ☐ `video-processing-flow.json` (scheduled queue health checks)
  - ☐ `system-monitoring-flow.json` (provider health / error-rate alerts)
- ☐ Configure credentials: backend API base URL + service credential, OAuth2 email credential.
- ☐ Activate the workflows; trigger a test job and confirm the notification email arrives.
- ☐ Known gaps (2026-10-14): the video flow has a placeholder `workflowId "email-notification-flow"` (re-select the real workflow after import); the webhook path `job-completed` has no backend receiver (n8n-side only); the "Has New Video?" false branch is unwired. Never assume n8n works from the JSON files alone — a live run is required.

## Step 8 — Post-deploy verification

- ☐ `GET /api/health` → 200. `GET /ready` → 200 only when DB + Redis answer.
- ☐ Register/login in the UI → `/dashboard` loads your (empty) video list.
- ☐ Upload a short video → `/processing/[jobId]` shows live stage progress → `/result/[jobId]` shows the recap + download buttons. **Expect a 30–60s+ cold start** if the services were asleep.
- ☐ If a job stays `queued` for > 5 min while the worker is awake → check that `CELERY_BROKER_URL` is identical on both Render services, Upstash is reachable, and the worker logs show `celery@… ready`.
- ☐ Admin: log in as the admin user → `/admin` shows overview/jobs/providers/feedback/analytics/errors.
- ☐ Submit a test bug report (`/contact`) and a 1–3 star rating on the result page.
- ☐ **RLS cross-user test (live):** two users A, B; A uploads; as B: `GET /api/videos/{A video}` → 404, `/api/jobs/{A job}` → 404, `/api/results/{A job}` → 404; B's list must not contain A's video. As A: own resources → 200.
- ☐ **CORS preflight check (live):** an OPTIONS preflight from a non-listed origin must NOT return a credentialed `allow-origin`.
- ☐ Confirm `DEV_AUTH_BYPASS=0` and `ENV=production` on **both** Render services; confirm `CORS_ORIGINS` contains no `*.pages.dev` wildcard.
- ☐ **Real AI check (required before calling staging ready):** with a live owner API key configured, run one real video end-to-end and confirm the recap contains a genuine AI-generated summary, highlights, and subtitles — NOT the degraded skeleton (`degraded:true`) and NOT a stubbed highlight.

---

## Environment variable table

> Verified against `backend/config.py` + `.env.example` 2026-10-15. The previous table listed variables the app never reads (`EMAIL_CLIENT_ID`, `MAX_UPLOAD_MB`, `MAX_VIDEO_MINUTES`, `MAX_JOBS_PER_DAY`) — those names are **wrong**; use the real names below. `SUPABASE_JWT_SECRET` is optional (leave empty to verify Supabase tokens via JWKS/RS256). `.env.example` contains **78 unique keys, zero duplicates** (verified 2026-10-15). ⚠️ `R2_BUCKET_PROCESSING` / `R2_BUCKET_THUMBNAILS` appear in `.env.example` but are **NOT read** by `backend/config.py` — do not set them expecting effect. `OLLAMA_URL` is read via `os.environ` in the vision agent, not via `Settings`.

| Variable | Where | Secret? | Example / notes |
|----------|-------|---------|-----------------|
| `ENV` | backend | no | `production` (disables dev-only `create_all` + auth bypass) |
| `API_BASE_URL` | backend | no | public backend URL; used to build local download links |
| `DATABASE_URL` | backend | ✅ | Supabase pooled Postgres URL (port 6543) |
| `SUPABASE_URL` | backend | no | `https://xyz.supabase.co` |
| `SUPABASE_KEY` | backend | ✅ | **service_role** key — backend only, bypasses RLS |
| `SUPABASE_ANON_KEY` | backend | no | anon/public key |
| `SUPABASE_JWT_SECRET` | backend | ✅ | optional; empty = JWKS/RS256 verification |
| `SUPABASE_STORAGE_BUCKET` | backend | no | `recap-results` (single bucket used for Supabase Storage) |
| `STORAGE_PROVIDER` | backend | no | `local` \| `r2` \| `supabase` |
| `STORAGE_ROOT` | backend | no | local fallback root (default `<repo>/storage`) |
| `REDIS_URL` | backend, celery, beat | ✅ | managed Redis URL (progress pub/sub) |
| `CELERY_BROKER_URL` | backend, celery, beat | ✅ | **must** be set on all three services — backend enqueues via this, not `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | backend, celery, beat | ✅ | usually same host, db 1 |
| `GEMINI_API_KEY` + `GEMINI_KEY_01..03` | backend | ✅ | primary + rotation pool |
| `GEMINI_MODEL` | backend | no | `gemini-2.0-flash` |
| `GROQ_API_KEY` + `GROQ_KEY_01..02` | backend | ✅ | Groq free key(s) |
| `OPENROUTER_API_KEY` + `OPENROUTER_KEY_01..02` | backend | ✅ | OpenRouter free key(s) |
| `HF_TOKEN` | backend | ✅ | Hugging Face read token |
| `PROVIDER_HEALTH_CHECK_SECONDS` | backend | no | `300` |
| `EMAIL_ENABLED` | backend | no | `false` = log-only, no mail sent |
| `EMAIL_PROVIDER` | backend | no | `gmail` \| `msgraph` \| `none` |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_SENDER` | backend | secret/secret/secret/no | Gmail OAuth2 (refresh-token flow) |
| `MSGRAPH_TENANT_ID` / `MSGRAPH_CLIENT_ID` / `MSGRAPH_CLIENT_SECRET` / `MSGRAPH_SENDER` | backend | no/no/secret/no | Microsoft Graph (client-credentials flow) |
| `R2_ACCOUNT_ID` | backend | no | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | backend | ✅ | R2 API token key |
| `R2_SECRET_ACCESS_KEY` | backend | ✅ | R2 API token secret |
| `R2_BUCKET_UPLOADS` / `R2_BUCKET_RESULTS` / `R2_BUCKET_TEMP` | backend | no | `recap-uploads` / `recap-results` / `recap-temporary` (only three the app uses) |
| `MAX_UPLOAD_BYTES` | backend | no | `2147483648` (2 GiB) |
| `MAX_VIDEO_DURATION_SEC` | backend | no | `1800` (30 min) |
| `UPLOAD_CHUNK_SIZE` | backend | no | `2097152` |
| `MAX_UPLOADS_PER_DAY` / `MAX_PROCESSING_MINUTES_PER_DAY` / `MAX_AI_REQUESTS_PER_DAY` | backend | no | `5` / `60` / `100` fair-use caps |
| `RATE_LIMIT_DEFAULT` / `RATE_LIMIT_UPLOAD` | backend | no | `120/minute` / `10/minute` (per-IP, slowapi) |
| `CORS_ORIGINS` | backend | no | exact frontend origin(s); see SECURITY.md re `*.pages.dev` + credentials |
| `ADMIN_EMAILS` | backend | no | comma-separated admin emails |
| `DEV_AUTH_BYPASS` | backend | no | `0` in production — never `1` |
| `RECAP_API_SERVICE_TOKEN` | backend + n8n | ✅ | machine-to-machine token for n8n monitoring flow (`openssl rand -hex 32`) |
| `WORKER_GATEWAY_TOKEN` | backend | ✅ | shared community-worker gateway token; empty = worker endpoints disabled |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | backend | no | `base` / `cpu` |
| `DEFAULT_OUTPUT_LANG` | backend | no | `en` \| `my` |
| `NEXT_PUBLIC_SUPABASE_URL` | frontend (Pages) | no | same as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | frontend (Pages) | no | anon key only |
| `NEXT_PUBLIC_API_URL` | frontend (Pages) | no | `https://api.example.com` — **must be set in production** (fallback is `http://localhost:8000`) |
| `NEXT_PUBLIC_DEFAULT_LOCALE` | frontend | no | `my` \| `en` |
| `RECAP_API_URL` (n8n-only) | n8n | no | backend base URL the n8n flows call |
| `RECAP_ALERT_WEBHOOK_URL` (n8n-only) | n8n | ✅ | ops alert webhook for the monitoring flow |

All values in `.env.example` are fake placeholders. Real values live **only** in `.env` (git-ignored, local dev) or the cloud provider's secret manager.

---

## Troubleshooting (quick reference)

| Symptom | Likely cause / fix |
|---|---|
| Jobs stay `queued` forever | Redis / Celery worker / Beat not running; `CELERY_BROKER_URL` not set on backend; worker service asleep (free tier) — wait for cold start, then check `CELERY_BROKER_URL` identical on both services + Upstash reachable + worker logs `celery@… ready` |
| `/api/admin/*` 403 | Non-admin user — check `ADMIN_EMAILS` / `app_metadata.is_admin` |
| Upload 400 | File format / size / duration limit exceeded |
| AI stages degrade (`degraded:true`) | No AI key, or all providers failed — read the `error` field for the real reason |
| `"no highlights to render"` | AI produced no highlights (expected when no key is configured) — not a render bug |
| Frontend progress never moves | SSE `event: progress` — fixed in this pass; polling fallback exists (see `frontend/hooks/useJobStream.ts`) |
| Result link 404 | Must use `latest_job.id`, not the video id — fixed in this pass |
| Migration re-run fails | Non-idempotent — run exactly once on a fresh project |
| `docker compose up` fails | No real `.env` — copy `.env.example` to `.env` and fill it in |
| Frontend calls `localhost:8000` in production | `NEXT_PUBLIC_API_URL` not set in the frontend host env **before the build** (baked at build time — rebuild/redeploy after setting it) |
| CORS preflight from a non-listed origin returns a credentialed `allow-origin` | Wildcard or wrong origin in `CORS_ORIGINS` — must be exact origin(s) only; a wildcard in `CORS_ORIGINS` now raises at startup |
