"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { listVideos } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import type { VideoItem } from "@/lib/types";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import StatCard from "@/components/StatCard";
import Card from "@/components/Card";
import Button from "@/components/Button";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";

interface DownloadEntry {
  title: string;
  kind: "video" | "subtitle";
  at: string;
}

function statusBadge(status: string, t: (k: string) => string) {
  const map: Record<string, string> = {
    completed: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
    processing: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300",
    queued: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
    failed: "bg-red-500/15 text-red-600 dark:text-red-300",
  };
  const cls = map[status] ?? "bg-[var(--surface-2)] text-[var(--muted)]";
  const label = t(`dashboard.status.${status}`) || status;
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${cls}`}>{label}</span>
  );
}

function DashboardContent() {
  const { t } = useT();
  const { user, profile, getAccessToken } = useAuth();
  const router = useRouter();
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [downloads, setDownloads] = useState<DownloadEntry[]>([]);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const token = await getAccessToken();
      const list = await listVideos(token);
      setVideos(list);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    try {
      const raw = window.localStorage.getItem("download_history");
      if (raw) setDownloads(JSON.parse(raw));
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const total = videos.length;
  const completed = videos.filter((v) => v.status === "completed").length;
  const processing = videos.filter(
    (v) => v.status === "processing" || v.status === "queued"
  ).length;
  const totalDuration = videos.reduce((s, v) => s + (v.duration_sec ?? 0), 0);
  const recent = [...videos]
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
    .slice(0, 5);
  const recentCompleted = recent.filter((v) => v.status === "completed");

  const displayName = profile?.display_name || user?.email?.split("@")[0] || "";

  return (
    <div>
      {/* Welcome header */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative mb-8 overflow-hidden rounded-3xl border border-indigo-500/25 bg-gradient-to-br from-blue-600/15 via-indigo-600/10 to-violet-600/15 p-8"
      >
        <div aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-violet-500/25 blur-[80px]" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
              {t("dashboard.greeting")}, {displayName} 👋
            </h1>
            <p className="mt-1.5 text-[var(--muted)]">{t("dashboard.subtitle")}</p>
          </div>
          <Button onClick={() => router.push("/upload")} className="shrink-0">
            ⬆️ {t("dashboard.uploadCta")}
          </Button>
        </div>
      </motion.div>

      {/* Stat cards */}
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("dashboard.stats.total")} value={total} icon="🎬" />
        <StatCard
          label={t("dashboard.stats.completed")}
          value={completed}
          icon="✅"
          accent="bg-emerald-500/15"
        />
        <StatCard
          label={t("dashboard.stats.processing")}
          value={processing}
          icon="⚙️"
          accent="bg-indigo-500/15"
        />
        <StatCard
          label={t("dashboard.stats.storage")}
          value={formatDuration(totalDuration)}
          icon="💾"
          accent="bg-violet-500/15"
          sub={t("dashboard.stats.total")}
        />
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[0, 1].map((i) => (
            <div key={i} className="card p-5">
              <div className="skeleton mb-3 h-6 w-2/3" />
              <div className="skeleton h-4 w-1/2" />
              <div className="skeleton mt-4 h-10 w-full" />
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState message={t("errors.loadFailed")} onRetry={load} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Recent videos */}
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">{t("dashboard.recentVideos")}</h2>
              <Link
                href="/dashboard/videos"
                className="text-sm font-semibold text-indigo-500 hover:underline dark:text-indigo-300"
              >
                {t("dashboard.viewAll")} →
              </Link>
            </div>
            {recent.length === 0 ? (
              <EmptyState
                icon="🎬"
                title={t("dashboard.emptyVideosTitle")}
                description={t("dashboard.emptyVideosDesc")}
                actionLabel={t("dashboard.emptyVideosCta")}
                onAction={() => router.push("/upload")}
              />
            ) : (
              <ul className="space-y-3">
                {recent.map((v) => (
                  <li
                    key={v.id}
                    className="flex items-center gap-3 rounded-xl p-2 transition-colors hover:bg-[var(--surface-2)]"
                  >
                    <div
                      aria-hidden
                      className="flex h-12 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-[var(--surface-2)] text-xl"
                    >
                      {v.thumbnail_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={v.thumbnail_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        "🎬"
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">{v.title}</p>
                      <p className="text-xs text-[var(--muted)]">
                        {formatDate(v.created_at)}
                        {v.duration_sec ? ` · ${formatDuration(v.duration_sec)}` : ""}
                      </p>
                    </div>
                    {statusBadge(v.status, t)}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="space-y-6">
            {/* Recent summaries */}
            <Card>
              <h2 className="mb-4 text-lg font-bold">{t("dashboard.recentSummaries")}</h2>
              {recentCompleted.length === 0 ? (
                <EmptyState
                  icon="📝"
                  title={t("dashboard.emptySummariesTitle")}
                  description={t("dashboard.emptySummariesDesc")}
                />
              ) : (
                <ul className="space-y-2">
                  {recentCompleted.slice(0, 4).map((v) => (
                    <li key={v.id}>
                      <Link
                        // /result/[jobId] needs a JOB id (video id 404s).
                        href={
                          v.latest_job?.id
                            ? `/result/${v.latest_job.id}`
                            : "/dashboard"
                        }
                        className="flex items-center justify-between gap-3 rounded-xl p-2.5 transition-colors hover:bg-[var(--surface-2)]"
                      >
                        <span className="truncate text-sm font-medium">✨ {v.title}</span>
                        <span aria-hidden className="text-[var(--muted)]">→</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {/* Download history */}
            <Card>
              <h2 className="mb-4 text-lg font-bold">{t("dashboard.downloadHistory")}</h2>
              {downloads.length === 0 ? (
                <EmptyState
                  icon="⬇️"
                  title={t("dashboard.emptyHistoryTitle")}
                  description={t("dashboard.emptyHistoryDesc")}
                />
              ) : (
                <ul className="space-y-2">
                  {downloads.slice(0, 5).map((d, i) => (
                    <li
                      key={i}
                      className="flex items-center gap-3 rounded-xl p-2 text-sm"
                    >
                      <span aria-hidden>{d.kind === "video" ? "🎬" : "💬"}</span>
                      <span className="min-w-0 flex-1 truncate">{d.title}</span>
                      <span className="shrink-0 text-xs text-[var(--muted)]">
                        {formatDate(d.at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <AppShell>
        <DashboardContent />
      </AppShell>
    </RequireAuth>
  );
}
