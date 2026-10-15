"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { listVideos } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import type { VideoItem } from "@/lib/types";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import Card from "@/components/Card";

/** Results page: completed recaps that have a result to view. */
function ResultsContent() {
  const { t } = useT();
  const { getAccessToken } = useAuth();
  const router = useRouter();
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const token = await getAccessToken();
      const list = await listVideos(token);
      setVideos(
        list
          .filter((v) => v.status === "completed")
          .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
      );
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          {t("sidebar.results")}
        </h1>
        <p className="mt-1 text-[var(--muted)]">{t("empty.resultsDesc")}</p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-4">
              <div className="skeleton h-5 w-1/2" />
              <div className="skeleton mt-2 h-4 w-1/3" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState message={t("errors.loadFailed")} onRetry={load} />
      ) : videos.length === 0 ? (
        <EmptyState
          icon="✨"
          title={t("empty.resultsTitle")}
          description={t("empty.resultsDesc")}
          actionLabel={t("empty.resultsCta")}
          onAction={() => router.push("/upload")}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {videos.map((v) => (
            <Card key={v.id} hover className="flex gap-4 p-4">
              <div
                aria-hidden
                className="flex h-20 w-32 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[var(--surface-2)] text-3xl"
              >
                {v.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={v.thumbnail_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  "✨"
                )}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-bold">{v.title}</h3>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {formatDate(v.created_at)}
                  {v.duration_sec ? ` · ${formatDuration(v.duration_sec)}` : ""}
                </p>
                <button
                  onClick={() =>
                    router.push(
                      v.latest_job?.id ? `/result/${v.latest_job.id}` : "/dashboard"
                    )
                  }
                  className="mt-2 text-sm font-bold text-indigo-500 hover:underline dark:text-indigo-300"
                >
                  {t("common.seeDetails")} →
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ResultsPage() {
  return (
    <RequireAuth>
      <AppShell>
        <ResultsContent />
      </AppShell>
    </RequireAuth>
  );
}
