"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import {
  adminAnalytics,
  adminErrors,
  adminFeedback,
  adminJobs,
  adminOverview,
  adminProviders,
} from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type {
  AdminJob,
  AdminOverview,
  AnalyticsData,
  ErrorLogItem,
  FeedbackItem,
  ProviderStatus,
} from "@/lib/types";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import StatCard from "@/components/StatCard";
import DataTable from "@/components/DataTable";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import Button from "@/components/Button";

type Tab = "overview" | "jobs" | "providers" | "feedback" | "analytics" | "errors";

/** Backend provider status → badge variant. "unconfigured" = no key set up yet. */
function healthBadge(status: string, t: (k: string) => string) {
  const map: Record<string, string> = {
    healthy: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
    degraded: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
    down: "bg-red-500/15 text-red-600 dark:text-red-300",
  };
  const variant =
    status === "healthy" ? "healthy" : status === "unconfigured" ? "degraded" : "down";
  const label =
    variant === "healthy"
      ? t("admin.healthy")
      : variant === "degraded"
        ? t("admin.unconfigured")
        : t("admin.down");
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${map[variant]}`}>
      {label}
    </span>
  );
}

/** Simple CSS/SVG bar chart — no heavy chart library. */
function BarChart({ data, labels }: { data: number[]; labels: string[] }) {
  const max = Math.max(...data, 1);
  return (
    <div className="flex h-44 items-end gap-2" role="img" aria-label="bar chart">
      {data.map((v, i) => (
        <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
          <span className="text-xs font-bold tabular-nums">{v}</span>
          <motion.div
            initial={{ height: 0 }}
            whileInView={{ height: `${(v / max) * 100}%` }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: i * 0.05 }}
            className="w-full rounded-t-lg bg-gradient-to-t from-blue-600 to-violet-500"
            style={{ minHeight: v > 0 ? 6 : 2 }}
          />
          <span className="text-[10px] text-[var(--muted)]">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

function AdminContent() {
  const { t } = useT();
  const { profile, loading: authLoading, getAccessToken } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [jobFilter, setJobFilter] = useState("");
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [errors, setErrors] = useState<ErrorLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!authLoading && profile && !profile.is_admin) {
      router.replace("/dashboard");
    }
  }, [authLoading, profile, router]);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const token = await getAccessToken();
      const [ov, jb, pv, fb, an, er] = await Promise.all([
        adminOverview(token),
        adminJobs(token, jobFilter || undefined),
        adminProviders(token),
        adminFeedback(token),
        adminAnalytics(token),
        adminErrors(token),
      ]);
      setOverview(ov);
      setJobs(jb);
      setProviders(pv);
      setFeedback(fb);
      setAnalytics(an);
      setErrors(er);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (profile?.is_admin) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.is_admin, jobFilter]);

  if (authLoading || !profile) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div aria-hidden className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-500/30 border-t-indigo-500" />
      </div>
    );
  }

  if (!profile.is_admin) {
    return <ErrorState title={t("admin.accessDenied")} />;
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: t("admin.tabOverview") },
    { key: "jobs", label: t("admin.tabJobs") },
    { key: "providers", label: t("admin.tabProviders") },
    { key: "feedback", label: t("admin.tabFeedback") },
    { key: "analytics", label: t("admin.tabAnalytics") },
    { key: "errors", label: t("admin.tabErrors") },
  ];

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            🛡️ {t("admin.title")}
          </h1>
          <p className="mt-1 text-[var(--muted)]">{t("admin.subtitle")}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={load}>
          ↻ {t("common.retry")}
        </Button>
      </div>

      <div role="tablist" aria-label={t("admin.title")} className="mb-6 flex gap-1 overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-1">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            role="tab"
            aria-selected={tab === tb.key}
            onClick={() => setTab(tb.key)}
            className={`whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
              tab === tb.key
                ? "bg-gradient-to-r from-blue-600 to-violet-600 text-white shadow-glow"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-5">
              <div className="skeleton h-6 w-2/3" />
              <div className="skeleton mt-3 h-9 w-1/3" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState message={t("errors.loadFailed")} onRetry={load} />
      ) : (
        <>
          {tab === "overview" && overview && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard label={t("admin.cards.users")} value={overview.users} icon="👥" />
              <StatCard label={t("admin.cards.activeJobs")} value={overview.jobs_active} icon="⚙️" accent="bg-indigo-500/15" />
              <StatCard label={t("admin.cards.queueDepth")} value={overview.queue_depth} icon="📥" accent="bg-amber-500/15"
                sub={overview.queue_depths ? Object.entries(overview.queue_depths).map(([q, n]) => `${q.replace("_queue", "")}: ${n}`).join(" · ") : undefined} />
              <StatCard label={t("admin.cards.storage")} value={overview.storage.provider} icon="💾" accent="bg-violet-500/15" />
              <StatCard label={t("admin.cards.errors")} value={analytics?.errors.last_24h ?? 0} icon="⚠️" accent="bg-red-500/15" />
              <Card className="p-5">
                <p className="text-sm text-[var(--muted)]">{t("admin.cards.providerHealth")}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {overview.providers.length === 0 && <span className="text-sm text-[var(--muted)]">{t("admin.noData")}</span>}
                  {overview.providers.map((p) => {
                    // /api/admin/overview returns `name`; /api/admin/providers
                    // returns `provider`. Accept both.
                    const name = p.provider ?? p.name ?? "?";
                    return (
                      <span key={name} className="flex items-center gap-1.5 text-sm">
                        {name} {healthBadge(p.status, t)}
                      </span>
                    );
                  })}
                </div>
              </Card>
            </motion.div>
          )}

          {tab === "jobs" && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="mb-4 flex gap-2">
                {["", "queued", "processing", "completed", "failed"].map((s) => (
                  <button
                    key={s}
                    onClick={() => setJobFilter(s)}
                    className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition-all ${
                      jobFilter === s
                        ? "bg-gradient-to-r from-blue-600 to-violet-600 text-white"
                        : "bg-[var(--surface)] text-[var(--muted)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {s === "" ? t("admin.filterAll") : t(`dashboard.status.${s}`)}
                  </button>
                ))}
              </div>
              <DataTable<AdminJob>
                columns={[
                  { key: "id", header: t("admin.jobsTable.id"), render: (r) => <span className="font-mono text-xs">{r.id.slice(0, 8)}…</span> },
                  { key: "video", header: t("admin.jobsTable.video"), render: (r) => <span className="font-mono text-xs">{r.video_id.slice(0, 8)}…</span> },
                  { key: "user", header: t("admin.jobsTable.user"), render: (r) => <span className="font-mono text-xs text-[var(--muted)]">{r.user_id.slice(0, 8)}…</span> },
                  { key: "status", header: t("admin.jobsTable.status"), render: (r) => t(`dashboard.status.${r.status}`) ?? r.status },
                  { key: "stage", header: t("admin.jobsTable.stage"), render: (r) => <span className="text-[var(--muted)]">{r.stage}</span> },
                  { key: "progress", header: t("admin.jobsTable.progress"), render: (r) => <span className="tabular-nums">{Math.round(r.progress)}%</span> },
                  { key: "error", header: t("admin.jobsTable.error"), render: (r) => <span className="max-w-[16rem] truncate text-red-500">{r.error ?? "—"}</span> },
                  { key: "created", header: t("admin.jobsTable.created"), render: (r) => <span className="text-[var(--muted)]">{formatDate(r.created_at)}</span> },
                ]}
                rows={jobs}
                rowKey={(r) => r.id}
                emptyMessage={t("admin.noData")}
              />
            </motion.div>
          )}

          {tab === "providers" && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-4 md:grid-cols-2">
              {providers.length === 0 && (
                <div className="md:col-span-2">
                  <EmptyState icon="🔌" title={t("admin.tabProviders")} description={t("admin.noData")} />
                </div>
              )}
              {providers.map((p) => (
                <Card key={p.provider ?? p.name ?? "?"} className="p-5">
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold">{p.provider ?? p.name ?? "?"}</h3>
                    {healthBadge(p.status, t)}
                  </div>
                  <p className="mt-2 text-sm text-[var(--muted)]">
                    {t("admin.providersTable.latency")}: {p.latency_ms != null ? `${p.latency_ms} ms` : "—"}
                  </p>
                  <p className="text-sm text-[var(--muted)]">
                    {t("admin.providersTable.errorRate")}: {p.error_rate != null ? `${(p.error_rate * 100).toFixed(1)}%` : "—"}
                  </p>
                  {p.last_error && (
                    <p className="mt-1 truncate text-xs text-red-500">{p.last_error}</p>
                  )}
                  <p className="text-xs text-[var(--muted)]">
                    {t("admin.providersTable.lastCheck")}: {p.checked_at ? formatDate(p.checked_at) : "—"}
                  </p>
                </Card>
              ))}
            </motion.div>
          )}

          {tab === "feedback" && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <DataTable<FeedbackItem>
                columns={[
                  { key: "job", header: t("admin.feedbackTable.job"), render: (r) => <span className="font-mono text-xs">{r.job_id.slice(0, 8)}…</span> },
                  {
                    key: "rating",
                    header: t("admin.feedbackTable.rating"),
                    render: (r) => (
                      <span className="text-lg" aria-label={`${r.rating}/3`}>
                        {r.rating === 3 ? "😍" : r.rating === 2 ? "🙂" : "😐"}
                      </span>
                    ),
                  },
                  { key: "comment", header: t("admin.feedbackTable.comment"), render: (r) => <span className="text-[var(--muted)]">{r.comment || "—"}</span> },
                  { key: "date", header: t("admin.feedbackTable.date"), render: (r) => <span className="text-[var(--muted)]">{formatDate(r.created_at)}</span> },
                ]}
                rows={feedback}
                rowKey={(r, i) => `${r.job_id}-${i}`}
                emptyMessage={t("admin.noData")}
              />
            </motion.div>
          )}

          {tab === "analytics" && analytics && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-6 md:grid-cols-2">
              <Card className="p-6">
                <h3 className="mb-4 font-bold">{t("admin.analytics.dailyUsers")}</h3>
                <p className="text-4xl font-extrabold tabular-nums">{analytics.daily_users}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">{t("admin.analytics.dailyUsersHint")}</p>
              </Card>
              <Card className="p-6">
                <h3 className="mb-4 font-bold">{t("admin.analytics.processingVolume")}</h3>
                <p className="text-4xl font-extrabold tabular-nums">
                  {(analytics.processing_volume.seconds_last_7d / 60).toFixed(1)}
                  <span className="ml-1 text-base font-semibold text-[var(--muted)]">{t("admin.analytics.minutes")}</span>
                </p>
                <p className="mt-1 text-sm text-[var(--muted)]">{t("admin.analytics.processingVolumeHint")}</p>
              </Card>
              <Card className="p-6">
                <h3 className="mb-4 font-bold">{t("admin.analytics.aiUsage")}</h3>
                {Object.keys(analytics.ai_usage).length === 0 ? (
                  <p className="text-sm text-[var(--muted)]">{t("admin.noData")}</p>
                ) : (
                  <BarChart
                    data={Object.values(analytics.ai_usage)}
                    labels={Object.keys(analytics.ai_usage)}
                  />
                )}
              </Card>
              <Card className="p-6">
                <h3 className="mb-4 font-bold">{t("admin.analytics.errors24h")}</h3>
                <p className="text-4xl font-extrabold tabular-nums text-red-500">{analytics.errors.last_24h}</p>
              </Card>
            </motion.div>
          )}

          {tab === "errors" && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <DataTable<ErrorLogItem>
                columns={[
                  { key: "time", header: t("admin.errorsTable.time"), render: (r) => <span className="text-[var(--muted)]">{formatDate(r.created_at)}</span> },
                  { key: "source", header: t("admin.errorsTable.source"), render: (r) => <span className="font-mono text-xs">{r.source}</span> },
                  { key: "message", header: t("admin.errorsTable.message"), render: (r) => <span className="max-w-[28rem] truncate">{r.message}</span> },
                  { key: "job", header: t("admin.errorsTable.job"), render: (r) => <span className="font-mono text-xs">{r.job_id ? `${r.job_id.slice(0, 8)}…` : "—"}</span> },
                ]}
                rows={errors}
                rowKey={(r) => String(r.id)}
                emptyMessage={t("admin.noData")}
              />
            </motion.div>
          )}
        </>
      )}
    </div>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth>
      <AppShell>
        <AdminContent />
      </AppShell>
    </RequireAuth>
  );
}
