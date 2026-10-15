# AI Video Recap Platform

> ⛔ **NOT READY — not deployed, not a live service.** This repository contains the full source code of the platform, but nothing is deployed yet: no live URL, no production backend, no production frontend. Do not treat any URL in this repo as a live deployment unless it is explicitly confirmed elsewhere.

A **100% free** AI video recap platform. Upload a video, get an AI-generated recap with a Burmese (Myanmar) voiceover, burned-in subtitles, and downloadable MP4 + SRT output. Users never provide API keys — the owner manages all AI provider keys via environment variables only.

## What it is

- **Backend:** FastAPI + 8 AI agents (ingestion, processing/FFmpeg, speech, vision, summary, highlights, rendering, email) + Celery queue system (5 queues, priority, retry) + AI provider manager (Gemini / Groq / OpenRouter / Hugging Face with key rotation and health checks).
- **Frontend:** Next.js 14 + TypeScript + Tailwind — landing, auth, dashboard, upload, processing, result, admin. Burmese-first UI (Myanmar + English toggle), PWA-ready.
- **Data / infra:** Supabase Postgres (13 tables, Row Level Security) + Supabase Storage / Cloudflare R2 + Docker + docker-compose + GitHub Actions CI + 3 n8n automation workflows.
- **Email:** notification emails (OAuth2) when a recap is ready.
- **Docs:** full Burmese project report in [`PROJECT_COMPLETION_REPORT.md`](PROJECT_COMPLETION_REPORT.md) (also as PDF: `AI_VIDEO_RECAP_FINAL_PROJECT_REPORT.pdf`), deployment guide in [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md), test evidence in [`TEST_RESULTS.md`](TEST_RESULTS.md).

## Status

### Done
- Full codebase (backend + frontend + infra + docs).
- Bug-fix passes: CORS exact-allowlist, validated query params, upload size cap, notification status handling, and more (see the completion report).
- Local tests: **38 pytest passed**, frontend `tsc --noEmit` + production build pass, contract check matched.
- Local end-to-end smoke test on a self-generated 3-second video with a stubbed highlight stage (pipeline works end to end without AI keys).
- Supabase project set up (Singapore, free tier): migration applied once, private `recap-results` bucket created.
- Local git repo: branch `main`, first commit created (author: GitHub noreply address).

### Not done
- **Deployment** — no backend, frontend, Redis, or storage deployed anywhere.
- **Real AI recap** — a genuine AI recap has never been produced (no owner API key has been configured in any environment yet).
- **Docker image build** — never run (no Docker in the build environment).
- **Dependency audit** — pip-audit / npm audit not run to a clean result.
- **RLS cross-user test** — pending until the backend is deployed.
- **Auth providers** — Supabase Auth Email + Google providers not enabled yet; redirect URLs to be set after frontend deploy.
- **Email OAuth2 / n8n hosting** — not configured yet.

See §11 (Remaining Blockers) of [`PROJECT_COMPLETION_REPORT.md`](PROJECT_COMPLETION_REPORT.md) for the full list.

## Local setup (development only)

```bash
# 1. Copy the example env file and fill in real values ONLY on your own machine.
#    Never commit .env — it is git-ignored.
cp .env.example .env

# 2. Start everything (needs Docker).
docker compose up

# 3. Backend tests
backend/venv/bin/python -m pytest backend/tests -q

# 4. Frontend typecheck + production build
cd frontend && npx tsc --noEmit && npm run build
```

Full deployment instructions (hosting, Supabase, Redis, storage, secrets) are in [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md). Read it before deploying anything.

## Security

- **Never hardcode secrets.** No API keys, passwords, tokens, or service-role keys in code, chat, commits, or reports. All secrets go through environment variables or the hosting provider's secure Secrets settings.
- **No private security contact is published yet.** Do not post exploit details publicly. Once this repository is public on GitHub, report vulnerabilities via GitHub **private vulnerability reporting** (to be enabled when the repo is created). See [`docs/SECURITY.md`](docs/SECURITY.md).
- Run the secret scanner before committing: `python3 scripts/secret_scan.py` (must exit 0).

## ⚠️ Migration warning — read before touching the database

`supabase/migrations/001_init.sql` is **non-idempotent and has already been applied exactly once** to the live Supabase project. **Never re-run it** — re-running it will fail and could damage the live database. Future schema changes need a **new** follow-up migration file.

## License

**This repository has no license.** Public visibility alone does **not** grant permission to use, copy, modify, or distribute this code. All rights reserved unless the owner adds a license later.
