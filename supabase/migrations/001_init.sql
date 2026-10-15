-- ============================================================
-- AI Video Recap Platform — initial schema
--
-- *** NOT YET APPLIED ***
-- This migration has NOT been run against any database. Applying it
-- requires a Supabase project (USER ACTION):
--   1. Create a free project at https://supabase.com/dashboard
--   2. Open SQL Editor > New query, paste this file, run it
--      (or: supabase db push with the Supabase CLI)
--   3. Copy the project URL + keys into your .env
--
-- *** SCHEMA SOURCE OF TRUTH ***
-- This file mirrors backend/database/models.py EXACTLY:
--   - IDs are text (uuid strings), NOT uuid columns — the app's
--     SQLAlchemy models use String(64) for every id.
--   - jobs.priority is INTEGER (3 = normal), jobs.progress is FLOAT.
--   - Column names match the models (error_log / source / message /
--     detail, email_records.to_email / sent / error, etc.).
-- Do NOT "fix" this file by renaming columns to match the n8n
-- flows — the n8n flows were updated to match THIS schema.
--
-- Row Level Security is enabled on all user-data tables. The
-- service_role key bypasses RLS by default (backend + n8n use it);
-- the anon key is restricted to each user's own rows via
-- auth.uid()::text (ids are text, auth.uid() is uuid).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------- users ----------------
CREATE TABLE users (
    id           text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    email        text UNIQUE,
    display_name text,
    is_admin     boolean DEFAULT false NOT NULL,
    created_at   timestamptz DEFAULT now() NOT NULL
);

-- ---------------- videos ----------------
CREATE TABLE videos (
    id            text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id       text REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    original_name text,
    container     text,
    size_bytes    bigint,
    duration_sec  float,
    width         int,
    height        int,
    storage_path  text,
    sha256_prefix text,
    meta          jsonb NOT NULL DEFAULT '{}',
    created_at    timestamptz DEFAULT now() NOT NULL
);

-- ---------------- jobs ----------------
CREATE TABLE jobs (
    id          text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    video_id    text REFERENCES videos(id) ON DELETE CASCADE NOT NULL,
    user_id     text REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    status      text DEFAULT 'queued' NOT NULL,
    stage       text,
    progress    float DEFAULT 0 NOT NULL,
    priority    int DEFAULT 3 NOT NULL,
    error       text,
    output_lang text DEFAULT 'en' NOT NULL,
    -- Upload-time recap preferences (frontend upload form; backend Job
    -- subtitle_language / recap_style). Added before first application.
    subtitle_language text DEFAULT 'my' NOT NULL,
    recap_style text DEFAULT 'detailed' NOT NULL,
    result      jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz DEFAULT now() NOT NULL,
    updated_at  timestamptz DEFAULT now() NOT NULL
);

-- ---------------- outputs ----------------
CREATE TABLE outputs (
    id           text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id       text REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
    kind         text NOT NULL,
    storage_path text NOT NULL,
    download_url text,
    -- bigint: a max-size (2 GiB) file is 1 byte over Postgres int4 max.
    size_bytes   bigint,
    created_at   timestamptz DEFAULT now() NOT NULL
);

-- ---------------- api_usage ----------------
CREATE TABLE api_usage (
    id         bigserial PRIMARY KEY,
    user_id    text,
    job_id     text,
    provider   text,
    model      text,
    task       text,
    success    boolean,
    latency_ms int,
    tokens_in  int,
    tokens_out int,
    error      text,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- email_records ----------------
CREATE TABLE email_records (
    id         text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    text,
    job_id     text,
    to_email   text NOT NULL,
    subject    text NOT NULL,
    provider   text DEFAULT 'log' NOT NULL,
    sent       boolean DEFAULT false NOT NULL,
    error      text,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- feedback ----------------
CREATE TABLE feedback (
    id         text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    text,
    job_id     text,
    rating     int CHECK (rating IN (1, 2, 3)),
    comment    text,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- bug_reports ----------------
CREATE TABLE bug_reports (
    id         text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    text,
    subject    text,
    body       text,
    job_id     text,
    status     text DEFAULT 'open' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- feature_requests ----------------
CREATE TABLE feature_requests (
    id         text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    text,
    title      text,
    body       text,
    status     text DEFAULT 'open' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- provider_health ----------------
CREATE TABLE provider_health (
    id         bigserial PRIMARY KEY,
    provider   text UNIQUE NOT NULL,
    status     text DEFAULT 'unknown' NOT NULL,
    latency_ms int,
    error_rate float,
    last_error text,
    checked_at timestamptz
);

-- ---------------- community_workers ----------------
CREATE TABLE community_workers (
    id             text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name           text NOT NULL,
    worker_type    text NOT NULL,
    capabilities   jsonb NOT NULL DEFAULT '{}',
    status         text DEFAULT 'online' NOT NULL,
    last_heartbeat timestamptz,
    created_at     timestamptz DEFAULT now() NOT NULL
);

-- ---------------- error_log ----------------
-- NOTE: singular table name (matches backend/database/models.py).
-- Written by backend workers, the n8n flows, and admin tooling.
CREATE TABLE error_log (
    id         bigserial PRIMARY KEY,
    job_id     text,
    user_id    text,
    source     text NOT NULL,
    message    text NOT NULL,
    detail     text,
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ---------------- analytics_events ----------------
CREATE TABLE analytics_events (
    id         bigserial PRIMARY KEY,
    user_id    text,
    event      text NOT NULL,
    payload    jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz DEFAULT now() NOT NULL
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX idx_jobs_user_status      ON jobs (user_id, status);
CREATE INDEX idx_jobs_video            ON jobs (video_id);
CREATE INDEX idx_videos_user           ON videos (user_id);
CREATE INDEX idx_outputs_job           ON outputs (job_id);
CREATE INDEX idx_email_records_job     ON email_records (job_id);
CREATE INDEX idx_api_usage_created     ON api_usage (created_at);
CREATE INDEX idx_error_log_created     ON error_log (created_at);
CREATE INDEX idx_analytics_events_created ON analytics_events (created_at);

-- ============================================================
-- updated_at trigger for jobs
-- ============================================================
CREATE OR REPLACE FUNCTION set_jobs_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION set_jobs_updated_at();

-- ============================================================
-- Row Level Security
-- service_role bypasses RLS by default; the policies below
-- restrict the anon/authenticated key to each user's own rows.
-- ids are text, so auth.uid() is cast to text for comparison.
-- ============================================================
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos           ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE outputs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_records    ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback         ENABLE ROW LEVEL SECURITY;
ALTER TABLE bug_reports      ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_requests ENABLE ROW LEVEL SECURITY;
-- Service-only tables (no policies => anon key gets no access):
ALTER TABLE api_usage         ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_health   ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events  ENABLE ROW LEVEL SECURITY;

-- users: read + update own row only
CREATE POLICY users_select_own ON users
    FOR SELECT USING (auth.uid()::text = id);
CREATE POLICY users_update_own ON users
    FOR UPDATE USING (auth.uid()::text = id);

-- videos / jobs / feedback / bug_reports / feature_requests: owner-only
CREATE POLICY videos_owner ON videos
    FOR ALL USING (auth.uid()::text = user_id);
CREATE POLICY jobs_owner ON jobs
    FOR ALL USING (auth.uid()::text = user_id);
CREATE POLICY feedback_owner ON feedback
    FOR ALL USING (auth.uid()::text = user_id);
CREATE POLICY bug_reports_owner ON bug_reports
    FOR ALL USING (auth.uid()::text = user_id);
CREATE POLICY feature_requests_owner ON feature_requests
    FOR ALL USING (auth.uid()::text = user_id);

-- outputs: visible to the owner of the parent job
CREATE POLICY outputs_owner ON outputs
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.id = outputs.job_id
              AND j.user_id = auth.uid()::text
        )
    );

-- email_records: visible to the owner of the parent job
CREATE POLICY email_records_owner ON email_records
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.id = email_records.job_id
              AND j.user_id = auth.uid()::text
        )
    );
