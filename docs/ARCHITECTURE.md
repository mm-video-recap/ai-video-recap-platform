# ARCHITECTURE — Autonomous AI Video Recap Platform (deep dive)

Companion to the overview diagram in `docs/README.md`. This doc covers the 8 agents, queue topology, provider management, self-healing, the community worker network, AI memory, and analytics.

> NOTE (unverified against implementation): this describes the master contract the backend/frontend/infra subagents are building in parallel. Where code is still being written, names are the contract's; reconcile with `backend/` if they drift.

## 1. The 8 agents — responsibilities & data flow

A job flows through the agents in order. Each agent reads the job context, writes artifacts to storage, and publishes `{stage, progress, message}` events consumed by the SSE stream.

| # | Agent | Consumes → Produces |
|---|-------|---------------------|
| 01 | **Ingestion** | raw upload → validated video + metadata (container, duration, resolution, fps, audio presence). Rejects non-video/over-cap files with 422/413. |
| 02 | **Processing** | video → normalized assets: 16 kHz mono audio track, scene-split segments, thumbnails. |
| 03 | **Speech / Whisper** | audio → timestamped transcript (word-level where the model supports it). |
| 04 | **Vision** | sampled frames → scene descriptions, on-screen text (OCR), notable visual events. |
| 05 | **Summary** | transcript + vision notes → recap plan: title, highlight list `[{start, end, label}]`, Burmese narration script. Validates timestamps against real duration. |
| 06 | **Highlights** | recap plan + source → trimmed highlight clips, ordered for the final timeline. |
| 07 | **Rendering** | clips + TTS voiceover + subtitles → final MP4 (9:16 default / 16:9), burned-in or soft subtitles, audio ducking under narration. |
| 08 | **Email** | job completion/failure → notification email via OAuth2 provider (graceful no-op if email unconfigured). |

Data flow per job:

```
upload (multipart) ─► 01 ingestion ─► 02 processing ─┬─► 03 speech ─┐
                                                     └─► 04 vision ─┴─► 05 summary
                                                          ─► 06 highlights ─► 07 rendering
                                                          ─► artifacts (mp4, srt, script, thumbs)
                                                          ─► 08 email ─► user notified
```

Stages 03 and 04 run in parallel; everything else is sequential. All artifacts land under the job's storage prefix; intermediates in `temporary/` expire after 7 days.

## 2. Queue topology, priority & retry

Celery 5 with Redis broker. Five named queues (contract):

| Queue | Carries | Priority |
|-------|---------|----------|
| `video_upload_queue` | ingestion + validation tasks | high (short, user-waiting) |
| `video_processing_queue` | normalization, scene split, thumbnails | normal |
| `ai_analysis_queue` | whisper, vision, summary, highlights | normal, longest-running |
| `render_queue` | TTS + FFmpeg render | normal |
| `email_queue` | notifications | low |

- **Priorities:** within a queue, tasks carry a priority (0–9). User-facing short tasks (upload validation, status updates) outrank batch work.
- **Retry:** exponential backoff with jitter; max retries per stage (transient AI 503/429 → next provider, see §3, before retrying the same one). Dead-letter: after max retries the job is marked `failed`, the error is logged to `/api/admin/errors`, and agent 08 sends a failure email.
- **Idempotency:** every task key includes `job_id + stage`; workers check for existing artifacts before redoing work, so a crashed worker can safely resume.

## 3. AI provider manager — rotation & health checks

`backend/ai_provider/` centralizes all LLM/vision/TTS calls. Providers (contract): **Gemini** (primary, key pool `GEMINI_API_KEY` + `GEMINI_KEY_01..03`), **Groq**, **OpenRouter** (free models), **Hugging Face**.

- **Capability routing:** each provider declares capabilities (`transcribe`, `summarize`, `translate`, `vision`, `tts`); the manager routes each call to providers that support it.
- **Key rotation:** per-key usage/error counters. On 429/5xx or quota errors, the key is marked unhealthy and the next key/provider is tried immediately (failover, not retry-same).
- **Health checks:** every 5 minutes a lightweight probe runs per provider/key; results feed `GET /api/admin/providers` and auto-exclude sick providers from routing until they recover.
- **Fallback order** (contract default): Gemini → Groq → OpenRouter → Hugging Face; configurable per capability via env.
- **No user keys:** the system owner manages all keys via env/secrets manager. Users never supply keys (differs from BYOK prototypes — this is the platform rule).

## 4. Self-healing design

- **Worker crash:** Celery ack-late + idempotent stages → task re-queued, resumes from existing artifacts.
- **Provider outage:** failover chain (§3) + queued retry; job stays `processing`, SSE keeps the user informed.
- **Stuck jobs:** a watchdog task (n8n `video-processing-flow.json` or Celery beat) marks jobs with no heartbeat beyond N minutes as `failed` with a clear message, freeing the queue.
- **Storage:** `temporary/` lifecycle expiry (7 days, R2 rule or cron); failed-job artifacts are kept 24h for debugging then purged.
- **Deploys:** health endpoint `/api/health` gates load-balancer traffic; rolling restarts drain Celery workers first.

## 5. Community worker network

Volunteers donate CPU/GPU via a lightweight worker client (`backend/workers/`):

1. Admin issues a token out-of-band.
2. Worker calls `POST /api/workers/register` → receives `worker_id` + `X-Worker-Token`.
3. Worker heartbeats every ~15s (`POST /api/workers/{id}/heartbeat`) and long-polls `GET /api/workers/tasks/next` for tasks matching its `capabilities` (e.g. `whisper`, `render`).
4. Results are posted back; the backend verifies checksums before accepting artifacts.

Trust model: workers never see user PII (only opaque job ids + media chunks); admin can revoke a token instantly; suspicious output (checksum/format mismatch) quarantines the worker.

> NOTE (unverified against implementation): the exact result-postback endpoint and checksum scheme are not in the route contract — confirm in `backend/api/` before building a worker client.

## 6. AI memory — user preferences

The platform remembers per-user preferences to improve future recaps (opt-out in `/settings`):

- **Signals:** 1–3 star ratings (`POST /api/feedback`), chosen voice, subtitle on/off, aspect choice, re-downloads.
- **Storage:** Supabase table (user_id → preference JSON + rolling aggregates); RLS restricts to the owner.
- **Use:** the summary agent injects a compact preference summary into its prompt (e.g. "user prefers shorter recaps, female voice"); the rendering agent applies preferred aspect/voice defaults.
- **Privacy:** preferences are never sold/shared; deleting the account deletes the memory row.

## 7. Analytics events

Emitted per job (Supabase table, admin-visible at `GET /api/admin/analytics`):

- `job.created / job.stage_started / job.stage_completed / job.completed / job.failed`
- `provider.failover` (from → to, reason), `provider.health` (periodic snapshot)
- `user.feedback` (rating), `user.report` (bug/feature)
- `worker.registered / worker.heartbeat_lost`

Retention: raw events 90 days, aggregates indefinite. No PII in event payloads (user ids are UUIDs, no emails).
