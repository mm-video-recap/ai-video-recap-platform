# n8n Workflows — AI Video Recap Platform

Three automation flows that sit **outside** the main FastAPI/Celery stack and
handle polling, notifications, and monitoring. All flows are plain JSON
exports: import them into your own n8n instance.

> **BLOCKER — n8n hosting is a USER ACTION.** These files cannot run until a
> human provisions an n8n instance (n8n Cloud, or self-hosted via Docker:
> `docker run -p 5678:5678 n8nio/n8n`). Nothing here creates accounts,
> credentials, or hosted workflows automatically.

## The three flows

### 1. `video-processing-flow.json` — New-upload poller
Polls every minute for queued jobs (join: `videos` × `jobs WHERE status = 'queued'`), then for each:
1. `GET {RECAP_API_URL}/api/jobs/{job_id}` — fetch the job the API already
   created. **Job creation is API-owned**: `POST /api/videos/upload` creates
   the Video + Job rows and hands off to Celery; n8n never creates jobs.
2. Postgres: log `video_processing_started` into `analytics_events`.
3. `GET .../api/jobs/{job_id}` — polls the job status (not the SSE stream;
   EventSource is for browsers).
4. IF completed → executes the email-notification flow; otherwise → logs the
   incomplete job into `error_log` (Postgres, `source = 'n8n-video-flow'`).

Error branches: every HTTP node uses `onError: continueErrorOutput` and routes
failures into the **Log Pipeline Error** node (Postgres `error_log` insert).
The IF node's false branch on "Has New Video?" is intentionally unwired —
no new uploads means a silent skip.

### 2. `email-notification-flow.json` — Completion emails
Triggered by the webhook `POST /webhook/job-completed` (production path set
in the Webhook node). For each completed job:
1. `GET {RECAP_API_URL}/api/jobs/{job_id}` — job details.
2. Postgres: `SELECT email, display_name AS name FROM users WHERE id = ...`.
3. Builds the subject/body (HTML: title, summary, download link, minutes).
4. Sends via the **Gmail** node.
5. Inserts a row into `email_records` (`to_email`, `subject`, `provider`,
   `sent = true`).

Error branch: if Gmail fails, **Log Email Failure** writes a row with
`sent = false` and the error text into `email_records` so retries/audits can
find it.

### 3. `system-monitoring-flow.json` — 5-minute health watchdog
Every 5 minutes:
1. `GET {RECAP_API_URL}/health` → API status.
2. `GET {RECAP_API_URL}/api/admin/overview` → `queue_depth` (admin token).
3. `GET {RECAP_API_URL}/api/admin/providers` → provider health.
4. Postgres: rows in `error_log` from the last 5 minutes.
5. IF the API is not `ok` OR recent errors exist → build an alert payload
   (`severity: critical|warning`) → `POST` it to `{RECAP_ALERT_WEBHOOK_URL}`
   (your ops webhook: Slack/Discord/PagerDuty) → write a system log entry
   into `error_log`.

Error branches: a failed health check does **not** stop the flow — it
continues into the error scan so the alert logic still runs, and the alert
payload uses defensive lookups (`?.` / `??`) so an upstream failure can never
kill the alert itself. If the operator webhook itself fails, the flow still
writes the system log entry.

## How to import

1. In n8n: **Workflows → ⋯ → Import from file** (or paste the JSON).
2. Import order does not matter, except: the video flow references the email
   flow by name — after importing, open **Trigger Email Notification Flow**
   and re-select the imported `email-notification-flow` (workflow IDs differ
   per instance; the exported ID is a placeholder).
3. Set the required **environment variables** in n8n
   (Settings → n8n config / docker `-e` flags):
   - `RECAP_API_URL` — e.g. `https://api.yourdomain.com`
   - `RECAP_API_SERVICE_TOKEN` — bearer token the backend accepts for
     service calls (generate: `openssl rand -hex 32`; also put it in `.env`
     as `RECAP_API_SERVICE_TOKEN`)
   - `RECAP_ALERT_WEBHOOK_URL` — ops alert webhook (monitor flow only)
4. **Activate** each workflow (toggle in the top-right) — scheduled and
   webhook triggers do nothing until active.

## Credentials you must create (USER ACTION)

n8n credentials cannot be exported with values, so the JSONs contain
**placeholders** (`"id": null`, descriptive names). Create these in
n8n → Credentials, then open each flow and select them:

| Credential | Type | Used by |
|---|---|---|
| `Supabase Postgres` | Postgres | Fetch New Uploads (video flow); Fetch User Email, Log Email Record, Log Email Failure (email flow); Fetch Recent Errors, Create System Log Entry (monitor flow). Use the Supabase **connection string** (pooled, port 6543) or direct host. |
| `Gmail OAuth2` | Gmail OAuth2 | Send Completion Email (email flow). Create in Google Cloud Console; never use an app password. |
| `RECAP_API_SERVICE_TOKEN` (env, not a credential) | — | All backend HTTP calls (`Authorization: Bearer …`). |

## Notes / known gaps

- All backend endpoints referenced in the flows exist in the FastAPI app:
  `GET /health`, `GET /api/jobs/{id}`, `GET /api/admin/overview`,
  `GET /api/admin/providers`. The flows never create jobs — upload via
  `POST /api/videos/upload` owns job creation.
- All Postgres queries match `supabase/migrations/001_init.sql`
  (`error_log` singular, `error_log.source/message/detail`,
  `email_records.to_email/sent/error`, `users.display_name`).
- The `Check Queue Status` / `Check AI Provider Health` HTTP nodes call
  **admin** endpoints with `Authorization: Bearer <RECAP_API_SERVICE_TOKEN>`.
  The backend accepts that token as the service identity `service:n8n`
  (admin) when `RECAP_API_SERVICE_TOKEN` is set in the backend `.env`
  (see `backend/api/deps.py`); empty = disabled.
