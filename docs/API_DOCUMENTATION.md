# API DOCUMENTATION — Autonomous AI Video Recap Platform

Base URL: `https://<backend-host>` (local: `http://localhost:8000`). All paths below are prefixed with `/api`.

**Auth:** Supabase JWT — send `Authorization: Bearer <supabase_access_token>` unless noted. The backend verifies the JWT; it does **not** issue tokens (no backend register/login).

> NOTE (unverified against implementation): exact error payload shapes, pagination params, and admin-role claim name are per the master contract; the backend is being built in parallel — verify against `/docs` (Swagger) on a running server.

Common error codes:

| Status | Meaning |
|--------|---------|
| 400 | Bad request (validation failed) |
| 401 | Missing/invalid/expired JWT |
| 403 | Forbidden (not owner, or not admin for `/api/admin/*`) |
| 404 | Video/job/result not found |
| 409 | Conflict (e.g. duplicate upload in progress) |
| 413 | File too large (over `MAX_UPLOAD_MB`) |
| 422 | File rejected (not a video / failed validation) |
| 429 | Rate limited (fair-use cap hit) |
| 500 | Internal error |
| 503 | AI providers unavailable / queue overloaded |

Error body shape (all errors):

```json
{ "detail": "human-readable message", "code": "UPLOAD_TOO_LARGE" }
```

---

## Health

### `GET /api/health`
No auth. Liveness probe for deploys/load balancers.

Response `200`:
```json
{ "status": "ok", "version": "1.0.0", "queues": "up", "db": "up" }
```

## Auth

### `GET /api/auth/me`
Auth: **required**. Returns the caller's profile from Supabase.

Response `200`:
```json
{ "id": "user-uuid", "email": "user@example.com", "created_at": "2026-10-14T12:00:00Z", "is_admin": false, "jobs_today": 1, "jobs_limit": 5 }
```

## Videos

### `POST /api/videos/upload`
Auth: **required**. `Content-Type: multipart/form-data`, single field **`file`** (the video).

Request: binary upload. Limits: container mp4/mov/webm/mkv, ≤ `MAX_UPLOAD_MB`, ≤ `MAX_VIDEO_MINUTES` duration.

Response `201`:
```json
{ "video_id": "vid_9f3a…", "job_id": "job_51c2…", "estimated_seconds": 240 }
```
A processing job is created automatically; poll `GET /api/jobs/{id}` or stream SSE.

### `GET /api/videos`
Auth: **required**. Lists the caller's videos (newest first).

Response `200`:
```json
{ "videos": [ { "id": "vid_9f3a…", "filename": "clip.mp4", "duration_s": 312.5, "status": "ready", "created_at": "2026-10-14T12:00:00Z", "thumbnail_url": "https://…" } ] }
```

### `GET /api/videos/{id}`
Auth: **required** (owner only). Single video metadata + related job ids.

Response `200`:
```json
{ "id": "vid_9f3a…", "filename": "clip.mp4", "duration_s": 312.5, "width": 1280, "height": 720, "status": "ready", "job_ids": ["job_51c2…"] }
```

### `DELETE /api/videos/{id}`
Auth: **required** (owner only). Deletes the video, its jobs, results and stored files.

Response `200`: `{ "deleted": true, "id": "vid_9f3a…" }`

## Jobs

### `GET /api/jobs/{id}`
Auth: **required** (owner only). Job status + per-stage progress.

Response `200`:
```json
{
  "id": "job_51c2…", "video_id": "vid_9f3a…", "status": "processing",
  "stage": "voice", "progress": 62,
  "stages": [
    { "name": "extract", "status": "done", "progress": 100 },
    { "name": "transcribe", "status": "done", "progress": 100 },
    { "name": "analyze", "status": "done", "progress": 100 },
    { "name": "voice", "status": "running", "progress": 40 },
    { "name": "render", "status": "queued", "progress": 0 }
  ],
  "created_at": "2026-10-14T12:01:00Z", "updated_at": "2026-10-14T12:05:00Z",
  "error": null
}
```
`status`: `queued | processing | done | failed | cancelled`.

### `GET /api/jobs/{id}/stream?token=`
Auth: via `token` query param (Supabase access token — EventSource cannot set headers, so the token travels in the URL; use HTTPS only, short-lived tokens recommended). Server-Sent Events stream.

Events (JSON per `data:` line):
```json
{ "stage": "voice", "progress": 45, "message": "မြန်မာအသံဖြင့် ပြောင်းနေပါသည်…" }
```
Terminal event: `{ "stage": "done", "progress": 100, "message": "ready", "result_url": "/api/results/job_51c2…" }` or `{ "stage": "failed", "progress": 100, "message": "…", "error": "…" }`.

## Results

### `GET /api/results/{job_id}`
Auth: **required** (owner only). The finished recap.

Response `200`:
```json
{
  "job_id": "job_51c2…",
  "title": "ဗီဒီယို အကျဉ်းချုပ်",
  "video_url": "https://…/recap.mp4",
  "srt_url": "https://…/recap.srt",
  "script_text": "…burmese narration…",
  "duration_s": 28.2, "aspect": "9:16",
  "highlights": [ { "start": 12.0, "end": 24.5, "label": "…" } ]
}
```

## Feedback & reports

### `POST /api/feedback`
Auth: **required**. Rate a finished recap (feeds the AI memory loop).

Request:
```json
{ "job_id": "job_51c2…", "rating": 2, "comment": "အသံနည်းနည်း မြန်နေတယ်" }
```
`rating`: 1–3 required; `comment` optional. Response `201`: `{ "ok": true }`.

### `POST /api/reports/bug`
Auth: optional (logged-in preferred). File a bug report.

Request:
```json
{ "title": "Upload stuck at 99%", "description": "…", "job_id": "job_51c2…", "contact_email": "user@example.com" }
```
Response `201`: `{ "ok": true, "report_id": "rep_…" }`.

### `POST /api/reports/feature`
Auth: optional. Request a feature. Same shape as bug report minus `job_id`.

## Admin (admin role required)

All `GET`, auth required + admin claim (403 otherwise).

| Method & path | Returns |
|---|---|
| `GET /api/admin/overview` | `{ users_total, jobs_today, jobs_failed_24h, queue_depth, storage_used_mb }` |
| `GET /api/admin/jobs` | paginated job list with filters (`?status=`, `?limit=`, `?offset=`) |
| `GET /api/admin/providers` | per-provider health: `{ name, status, latency_ms, keys_healthy, last_check }` |
| `GET /api/admin/feedback` | recent ratings/reports |
| `GET /api/admin/analytics` | usage aggregates (jobs/day, avg processing time, top errors) |
| `GET /api/admin/errors` | recent error log entries |

> NOTE (unverified against implementation): admin-role source (Supabase `app_metadata` claim vs DB table) is contract-level; confirm in `backend/security/`.

## Community workers

Workers are volunteer compute nodes. Auth: `X-Worker-Token: <token>` (issued out-of-band by the admin), **not** user JWT.

### `POST /api/workers/register`
Request: `{ "name": "my-gpu-box", "capabilities": ["whisper", "render"], "max_parallel": 2 }`
Response `201`: `{ "worker_id": "wrk_…", "token": "<worker-token>", "poll_interval_s": 15 }`

### `POST /api/workers/{id}/heartbeat`
Request: `{ "status": "idle", "load": 0.2 }` → Response `200`: `{ "ok": true }`

### `GET /api/workers/tasks/next`
Long-poll for the next queued task matching capabilities.
Response `200`: `{ "task": { "type": "transcribe", "job_id": "…", "payload": {…} } }` or `204` when empty.
