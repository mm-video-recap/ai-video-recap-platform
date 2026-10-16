"use client";

import type {
  AdminJob,
  AdminOverview,
  AnalyticsData,
  ErrorLogItem,
  FeedbackItem,
  JobStatus,
  ProviderStatus,
  RecapResult,
  UploadResult,
  UserProfile,
  VideoDetail,
  VideoItem,
} from "@/lib/types";

/** Backend base URL from env (public, no secrets). */
export function apiBase(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
    "http://localhost:8000"
  );
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.message === "string") return data.message;
  } catch {
    /* not json */
  }
  return `Request failed (${res.status})`;
}

async function apiFetch<T>(
  path: string,
  token: string | null,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    // Hard redirect to /login on 401 — EXCEPT for /api/auth/me itself.
    // /me IS the auth check: AuthProvider already handles its failure
    // (profile -> null). Redirecting on /me's own 401 creates an
    // infinite login<->dashboard reload loop (login sees a valid
    // Supabase session and bounces back to /dashboard, which calls /me
    // again). Live incident 2026-10-16: an ES256 token rejected by the
    // backend (RS256-only verifier) flickered exactly this way.
    if (path !== "/api/auth/me") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function apiGet<T>(path: string, token: string | null): Promise<T> {
  return apiFetch<T>(path, token, { method: "GET" });
}

export async function apiPost<T>(
  path: string,
  token: string | null,
  body?: unknown
): Promise<T> {
  return apiFetch<T>(path, token, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiDelete<T>(
  path: string,
  token: string | null
): Promise<T> {
  return apiFetch<T>(path, token, { method: "DELETE" });
}

/* ---------------- Public / health ---------------- */

export const getHealth = () =>
  apiGet<{ status: string; version: string }>("/api/health", null);

export const getMe = (token: string | null) =>
  apiGet<UserProfile>("/api/auth/me", token);

/* ---------------- Videos ---------------- */

export function uploadVideo(
  file: File,
  token: string,
  onProgress: (pct: number) => void,
  extra?: Record<string, string>
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    // Backend reads the recap preferences from QUERY params
    // (routes_videos.upload: output_lang, subtitle_language, recap_style,
    // intro_enabled, outro_enabled).
    // Any other keys in `extra` are sent as form fields (ignored by backend).
    const { output_lang, subtitle_language, recap_style,
            intro_enabled, outro_enabled, ...formExtra } =
      extra ?? {};
    const qs = new URLSearchParams();
    if (output_lang) qs.set("output_lang", output_lang);
    if (subtitle_language) qs.set("subtitle_language", subtitle_language);
    if (recap_style) qs.set("recap_style", recap_style);
    if (intro_enabled !== undefined) qs.set("intro_enabled", intro_enabled);
    if (outro_enabled !== undefined) qs.set("outro_enabled", outro_enabled);
    const qsStr = qs.toString();
    xhr.open(
      "POST",
      `${apiBase()}/api/videos/upload${qsStr ? `?${qsStr}` : ""}`
    );
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status === 201) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } catch {
          reject(new ApiError(xhr.status, "Invalid server response"));
        }
      } else if (xhr.status === 401 && typeof window !== "undefined") {
        window.location.href = "/login";
        reject(new ApiError(401, "Unauthorized"));
      } else {
        let msg = `Upload failed (${xhr.status})`;
        try {
          const data = JSON.parse(xhr.responseText);
          if (typeof data?.detail === "string") msg = data.detail;
        } catch {
          /* keep default */
        }
        reject(new ApiError(xhr.status, msg));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    const form = new FormData();
    form.append("file", file);
    if (formExtra) {
      for (const [k, v] of Object.entries(formExtra)) form.append(k, v);
    }
    xhr.send(form);
  });
}

export const listVideos = (token: string | null) =>
  apiGet<VideoItem[]>("/api/videos", token);

export const getVideo = (id: string, token: string | null) =>
  apiGet<VideoDetail>(`/api/videos/${id}`, token);

export const deleteVideo = (id: string, token: string | null) =>
  apiDelete<void>(`/api/videos/${id}`, token);

/* ---------------- Jobs ---------------- */

export const getJob = (id: string, token: string | null) =>
  apiGet<JobStatus>(`/api/jobs/${id}`, token);

export const streamUrl = (jobId: string, token: string) =>
  `${apiBase()}/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`;

export const getResult = (jobId: string, token: string | null) =>
  apiGet<RecapResult>(`/api/results/${jobId}`, token);

/* ---------------- Feedback & reports ---------------- */

export const postFeedback = (
  token: string | null,
  payload: { job_id: string; rating: 1 | 2 | 3; comment?: string }
) => apiPost<{ ok: boolean }>("/api/feedback", token, payload);

export const postBugReport = (
  token: string | null,
  payload: { subject: string; body: string; job_id?: string }
) => apiPost<{ ok: boolean }>("/api/reports/bug", token, payload);

export const postFeatureReport = (
  token: string | null,
  payload: { title: string; body: string }
) => apiPost<{ ok: boolean }>("/api/reports/feature", token, payload);

/* ---------------- Admin ---------------- */

export const adminOverview = (token: string | null) =>
  apiGet<AdminOverview>("/api/admin/overview", token);

export const adminJobs = (token: string | null, status?: string) =>
  apiGet<AdminJob[]>(
    `/api/admin/jobs${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    token
  );

export const adminProviders = (token: string | null) =>
  apiGet<ProviderStatus[]>("/api/admin/providers", token);

export const adminFeedback = (token: string | null) =>
  apiGet<FeedbackItem[]>("/api/admin/feedback", token);

export const adminAnalytics = (token: string | null) =>
  apiGet<AnalyticsData>("/api/admin/analytics", token);

export const adminErrors = (token: string | null, limit = 50) =>
  apiGet<ErrorLogItem[]>(`/api/admin/errors?limit=${limit}`, token);

export { ApiError };
