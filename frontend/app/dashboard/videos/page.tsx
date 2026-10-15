"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { deleteVideo, listVideos } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import type { VideoItem } from "@/lib/types";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Card from "@/components/Card";

function VideosContent() {
  const { t } = useT();
  const { getAccessToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<VideoItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const token = await getAccessToken();
      setVideos(await listVideos(token));
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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...videos].sort(
      (a, b) => +new Date(b.created_at) - +new Date(a.created_at)
    );
    if (!q) return sorted;
    return sorted.filter((v) => v.title.toLowerCase().includes(q));
  }, [videos, query]);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      const token = await getAccessToken();
      await deleteVideo(pendingDelete.id, token);
      setVideos((prev) => prev.filter((v) => v.id !== pendingDelete.id));
      toast(t("videos.deleted"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };

  const statusColor = (s: string) =>
    s === "completed"
      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
      : s === "failed"
        ? "bg-red-500/15 text-red-600 dark:text-red-300"
        : "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300";

  /** /result/[jobId] needs a JOB id — the video id will 404. The backend
   *  returns the latest job as latest_job; fall back to /dashboard when absent. */
  const openVideo = (v: VideoItem) => {
    const jobId = v.latest_job?.id;
    router.push(
      v.status === "completed" && jobId ? `/result/${jobId}` : "/dashboard"
    );
  };

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            {t("videos.title")}
          </h1>
          <p className="mt-1 text-[var(--muted)]">{t("videos.subtitle")}</p>
        </div>
        <Button onClick={() => router.push("/upload")}>⬆️ {t("sidebar.upload")}</Button>
      </div>

      <div className="mb-5">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("videos.searchPlaceholder")}
          aria-label={t("videos.searchPlaceholder")}
          className="input-field max-w-md"
        />
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-4">
              <div className="skeleton mb-3 aspect-video w-full" />
              <div className="skeleton h-5 w-3/4" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState message={t("errors.loadFailed")} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="🎬"
          title={t("empty.videosTitle")}
          description={t("empty.videosDesc")}
          actionLabel={t("empty.videosCta")}
          onAction={() => router.push("/upload")}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((v) => (
            <Card key={v.id} hover className="group overflow-hidden p-0">
              <button
                onClick={() => openVideo(v)}
                className="block w-full text-left"
                aria-label={`${t("videos.open")}: ${v.title}`}
              >
                <div className="relative aspect-video bg-[var(--surface-2)]">
                  {v.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={v.thumbnail_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full items-center justify-center text-4xl">🎬</div>
                  )}
                  <span
                    className={`absolute left-2 top-2 rounded-full px-2.5 py-1 text-xs font-semibold ${statusColor(v.status)}`}
                  >
                    {t(`dashboard.status.${v.status}`)}
                  </span>
                  {v.duration_sec ? (
                    <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs tabular-nums text-white">
                      {formatDuration(v.duration_sec)}
                    </span>
                  ) : null}
                </div>
                <div className="p-4">
                  <h3 className="truncate font-bold">{v.title}</h3>
                  <p className="mt-1 text-xs text-[var(--muted)]">{formatDate(v.created_at)}</p>
                </div>
              </button>
              <div className="flex gap-2 border-t divider p-3">
                <Button
                  variant="ghost"
                  size="sm"
                  className="flex-1"
                  onClick={() => openVideo(v)}
                >
                  {t("videos.open")} →
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setPendingDelete(v)}
                  aria-label={`${t("common.delete")}: ${v.title}`}
                >
                  🗑
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title={t("common.delete")}
      >
        <p className="text-sm text-[var(--muted)]">{t("videos.deleteConfirm")}</p>
        <p className="mt-2 truncate font-bold">{pendingDelete?.title}</p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setPendingDelete(null)}>
            {t("common.cancel")}
          </Button>
          <Button variant="danger" onClick={confirmDelete} loading={deleting}>
            {t("common.delete")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}

export default function VideosPage() {
  return (
    <RequireAuth>
      <AppShell>
        <VideosContent />
      </AppShell>
    </RequireAuth>
  );
}
