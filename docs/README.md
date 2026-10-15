# AI Video Recap Platform

**100% FREE, open-source AI video recap platform — autonomous multi-agent video summarization for everyone.**

Upload a video → 8 AI agents transcribe, analyze, highlight, and render a short recap video with Burmese/English narration and subtitles → download and share. No API keys required from users. No payment anywhere in the system.

> **Burmese-first:** the user interface defaults to မြန်မာ (Burmese) with an English toggle.

## Features

- **One-click recap** — upload MP4/MOV/WebM/MKV, get a shareable recap video with AI voiceover and subtitles.
- **8-agent autonomous pipeline** — ingestion → processing → speech (Whisper) → vision → summary → highlights → rendering → email notifications.
- **Free AI stack** — Gemini (rotating keys), Groq, OpenRouter free models, Hugging Face open models. System owner manages keys; users just register and use.
- **Live progress** — Server-Sent Events stream every pipeline stage with per-stage progress bars.
- **Burmese-first i18n** — Myanmar default, English toggle; Myanmar TTS voices.
- **Fair-use queue** — Redis + Celery with 5 priority queues; uploads accepted any size up to the configured cap.
- **Community workers** — volunteers can register GPU/CPU workers to donate compute (`POST /api/workers/register`).
- **Admin dashboard** — provider health, job queue, error rates, feedback analytics, usage reports.
- **Reports & feedback** — bug reports, feature requests, and 1–3 star recap ratings feed the AI memory loop.
- **PWA** — installable on phones, works from the browser.

## Architecture

```
 ┌──────────────┐
 │  Next.js 14  │  Burmese-first UI (/, /upload, /processing/[jobId],
 │  Frontend    │  /result/[jobId], /admin, …) · PWA
 └──────┬───────┘
        │ HTTPS / REST + SSE
 ┌──────▼───────┐   Supabase JWT Bearer
 │  FastAPI     │◄─────────────────────────┐
 │  Backend     │   auth only: GET /api/auth/me (no backend login)
 └──────┬───────┘                          │
        │                                  │
   ┌────▼────┐   ┌──────────────┐   ┌──────▼───────────┐
   │ Redis   │──►│ Celery 5x    │──►│ AI worker agents │
   │ (queues │   │ queues:      │   │ 01 ingestion     │
   │ +cache) │   │  upload      │   │ 02 processing    │
   └─────────┘   │  processing  │   │ 03 speech/whisper│
        │        │  ai_analysis │   │ 04 vision        │
        │        │  render      │   │ 05 summary       │
        │        │  email       │   │ 06 highlights    │
        └────────┼──────────────┘   │ 07 rendering     │
                 │ priorities+retry │ 08 email         │
                 └──────────────────┴──────────────────┘
        ┌────────▼────────┐    ┌──────────────────┐
        │ Supabase        │    │ Storage          │
        │ Postgres        │    │ local / R2 /     │
        │ (jobs, videos,  │    │ Supabase buckets │
        │  users, feedback│    │ uploads/results/ │
        │  analytics…)    │    │ temporary/…      │
        └─────────────────┘    └──────────────────┘
        ┌─────────────────────────────────────────┐
        │ AI Provider Manager (key rotation +     │
        │ health checks every 5 min):             │
        │ Gemini → Groq → OpenRouter → HuggingFace│
        └─────────────────────────────────────────┘
        ┌─────────────────────────────────────────┐
        │ Email (OAuth2 Gmail/Graph; graceful     │
        │ no-op when unconfigured) · n8n flows    │
        └─────────────────────────────────────────┘
```

Deep dive: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) · Deploy: [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)

## Tech Stack

| Layer      | Technology |
|------------|-----------|
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS, next-pwa |
| Backend    | FastAPI, Celery 5, Redis 7 |
| Auth       | Supabase Auth (JWT Bearer; backend verifies only) |
| Database   | Supabase free PostgreSQL (+ RLS) |
| Storage    | Local disk / Cloudflare R2 / Supabase Storage |
| AI         | Gemini (rotated keys), Groq, OpenRouter free tier, Hugging Face |
| Speech     | Faster-Whisper / Whisper, Edge TTS (my-MM voices) |
| Video      | FFmpeg |
| Email      | Gmail / Microsoft Graph via OAuth2 (no passwords) |
| Automation | n8n workflows (see `n8n/`) |
| Deploy     | Cloudflare Pages (frontend), HF Spaces / Render (backend), Supabase |

## Quickstart (local, Docker)

Prerequisites: Docker + Docker Compose, a free Supabase project (see [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)).

```bash
git clone <repo-url> AI-VIDEO-RECAP-PLATFORM
cd AI-VIDEO-RECAP-PLATFORM
cp .env.example .env        # fill in Supabase URL/keys + provider keys
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 · docs at http://localhost:8000/docs

> NOTE (unverified against implementation): Swagger UI path and exact compose service health ordering are as defined in `docker-compose.yml`; confirm on first run.

## Free-tier notes

- **Everything runs on free tiers**: Supabase free Postgres, Cloudflare Pages free, Cloudflare R2 free egress tier, Hugging Face Spaces free / Render free, free-tier AI APIs. No credit card, no payment code — the repo contains **zero** billing logic by design.
- Fair-use caps (configurable via env): max upload size, max video length, max recaps per user per day. When the queue is busy, jobs wait their turn — progress is always visible on `/processing/[jobId]`.
- Community workers: anyone can run a worker node and register it to donate compute to the public queue.

## Repo structure

```
AI-VIDEO-RECAP-PLATFORM/
├── frontend/            # Next.js 14 app (app router, TS, Tailwind, PWA)
├── backend/
│   ├── api/             # FastAPI route modules (videos, jobs, auth, admin, workers, reports…)
│   ├── agents/          # 8 pipeline agents (agent01_ingestion … agent08_email)
│   ├── ai_provider/     # provider manager: Gemini/Groq/OpenRouter/HF + rotation + health
│   ├── celery_app/      # Celery app, 5 queues, priorities, retry policy
│   ├── database/        # Supabase client, models, migrations (supabase/migrations/*.sql)
│   ├── security/        # JWT verification, rate limiting, upload validation
│   ├── workers/         # community worker client (register/heartbeat/task polling)
│   └── tests/
├── docs/                # README, deployment, API docs, guides (you are here)
├── scripts/             # contract_check.py, secret_scan.py (CI + local QA)
├── n8n/                 # email-notification, system-monitoring, video-processing flows
├── docker/              # Dockerfiles (backend, celery, frontend)
├── .github/workflows/   # CI: lint, tests, secret scan, contract check
├── docker-compose.yml   # local stack: redis, backend, celery, frontend
├── .env.example         # placeholder-only env template (never real keys)
└── storage/             # local dev storage (uploads/outputs/temporary)
```

## Docs index

| Doc | What it covers |
|-----|---------------|
| [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | User-action checklists: Cloudflare Pages, HF Spaces/Render, Supabase, R2, domain, n8n |
| [API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Every endpoint: method, auth, request/response shapes, errors |
| [USER_GUIDE.md](docs/USER_GUIDE.md) | End-user guide — Burmese first, then English |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 8 agents, queues, provider manager, self-healing, workers, AI memory, analytics |
| [PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md) | Add an AI provider, a processor agent, an exporter |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Code style, PR process, no-secrets rule |
| [SECURITY.md](docs/SECURITY.md) | Auth, RLS, rate limits, upload validation, abuse protection |

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). The golden rule: **secrets live in env only — never in code, never in a PR.** CI runs `scripts/secret_scan.py` on every push.

## License

> NOTE (unverified against implementation): no LICENSE file is in the repo yet — the intended license is MIT (free, open-source). Confirm with the project owner before publishing.
