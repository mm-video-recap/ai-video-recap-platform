/** Shared types matching the FastAPI backend contract. */

export interface UserProfile {
  id: string;
  email: string;
  is_admin: boolean;
  display_name: string;
}

export interface VideoItem {
  id: string;
  title: string;
  status: "queued" | "processing" | "completed" | "failed" | string;
  thumbnail_url?: string | null;
  created_at: string;
  duration_sec?: number | null;
  /** Latest job for this video (backend VideoSummary.latest_job). Its id — NOT
   *  the video id — is what /result/[jobId] and /api/results/{job_id} expect. */
  latest_job?: {
    id: string;
    status?: string;
    stage?: string | null;
    progress?: number | null;
  } | null;
}

export interface VideoDetail extends VideoItem {
  job_id?: string | null;
}

export type JobStatusName = "queued" | "processing" | "completed" | "failed";

export interface JobStatus {
  id: string;
  status: JobStatusName | string;
  stage: string;
  progress: number;
  error?: string | null;
  /** Upload-time recap preferences persisted on the backend Job. */
  subtitle_language?: string;
  recap_style?: string;
}

export interface StreamEvent {
  stage: string;
  progress: number;
  message?: string;
  /** Backend SSE payloads also carry the job status (queued/processing/completed/failed). */
  status?: string;
}

export interface TimelineChapter {
  start: number;
  end: number;
  label: string;
}

export interface Highlight {
  start: number;
  end: number;
  score: number;
}

export interface TranscriptCue {
  start: number;
  end: number;
  text: string;
}

export interface RecapResult {
  download_url: string;
  title: string;
  description: string;
  summary_short: string;
  summary_long: string;
  key_points: string[];
  timeline: TimelineChapter[];
  highlights: Highlight[];
  transcript: TranscriptCue[];
  subtitle_url?: string | null;
}

export interface UploadResult {
  video_id: string;
  job_id: string;
  estimated_seconds: number;
}

/** Matches GET /api/admin/overview exactly (backend/api/routes_admin.py). */
export interface AdminOverview {
  users: number;
  jobs_active: number;
  queue_depth: number;
  queue_depths?: Record<string, number>;
  providers: ProviderStatus[];
  // The backend deliberately does NOT expose the absolute storage root
  // (server-internal path); only the provider name is returned.
  storage: { provider: string; root?: string };
}

/** Matches GET /api/admin/jobs. */
export interface AdminJob {
  id: string;
  video_id: string;
  user_id: string;
  status: string;
  stage: string;
  progress: number;
  error?: string | null;
  created_at: string;
}

/** Matches GET /api/admin/providers. GET /api/admin/overview returns the same
 *  shape but with `name` instead of `provider` — both are accepted. */
export interface ProviderStatus {
  provider?: string;
  name?: string;
  status: "healthy" | "unhealthy" | "unconfigured" | string;
  latency_ms?: number | null;
  error_rate?: number | null;
  last_error?: string | null;
  checked_at?: string | null;
}

export interface FeedbackItem {
  id?: string | number;
  user_id?: string | null;
  job_id: string;
  rating: 1 | 2 | 3;
  comment?: string | null;
  created_at: string;
}

/** Matches GET /api/admin/analytics. */
export interface AnalyticsData {
  daily_users: number;
  processing_volume: { seconds_last_7d: number };
  ai_usage: Record<string, number>;
  errors: { last_24h: number };
}

/** Matches GET /api/admin/errors. */
export interface ErrorLogItem {
  id: number;
  job_id?: string | null;
  user_id?: string | null;
  source: string;
  message: string;
  created_at: string;
}

export type Locale = "my" | "en";

export type RecapStyle = "concise" | "detailed" | "highlights";

export interface RecapPreferences {
  summaryStyle: RecapStyle;
  defaultLanguage: "my" | "en";
}
