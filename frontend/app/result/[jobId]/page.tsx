"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { getResult, postFeedback } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import type { RecapResult } from "@/lib/types";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import VideoPlayer from "@/components/VideoPlayer";
import Button from "@/components/Button";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";

function recordDownload(title: string, kind: "video" | "subtitle") {
  try {
    const raw = window.localStorage.getItem("download_history");
    const list = raw ? JSON.parse(raw) : [];
    list.unshift({ title, kind, at: new Date().toISOString() });
    window.localStorage.setItem(
      "download_history",
      JSON.stringify(list.slice(0, 50))
    );
  } catch {
    /* ignore */
  }
}

function ResultContent({ jobId }: { jobId: string }) {
  const { t } = useT();
  const { getAccessToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [result, setResult] = useState<RecapResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [rating, setRating] = useState<1 | 2 | 3 | null>(null);
  const [comment, setComment] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [sendingFeedback, setSendingFeedback] = useState(false);

  const [seekTo, setSeekTo] = useState(0);
  const [playerKey, setPlayerKey] = useState(0);

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const token = await getAccessToken();
      setResult(await getResult(jobId, token));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const jumpTo = (time: number) => {
    setSeekTo(time);
    setPlayerKey((k) => k + 1);
  };

  const share = async () => {
    const url = `${window.location.origin}/result/${jobId}`;
    try {
      await navigator.clipboard.writeText(url);
      toast(t("result.linkCopied"), "success");
    } catch {
      toast(url, "info");
    }
  };

  const downloadFile = (url: string, filename: string, kind: "video" | "subtitle") => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.target = "_blank";
    document.body.appendChild(a);
    a.click();
    a.remove();
    recordDownload(result?.title || filename, kind);
    toast(t("common.download"), "success");
  };

  const sendFeedback = async () => {
    if (!rating) return;
    setSendingFeedback(true);
    try {
      const token = await getAccessToken();
      await postFeedback(token, {
        job_id: jobId,
        rating,
        comment: comment.trim() || undefined,
      });
      setFeedbackSent(true);
      toast(t("result.feedbackThanks"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setSendingFeedback(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton aspect-video w-full" />
        <div className="skeleton h-8 w-2/3" />
        <div className="skeleton h-24 w-full" />
      </div>
    );
  }

  if (error || !result) {
    return <ErrorState message={t("errors.loadFailed")} onRetry={load} />;
  }

  const ratingOptions: { value: 1 | 2 | 3; label: string; icon: string }[] = [
    { value: 3, label: t("result.feedbackExcellent"), icon: "😍" },
    { value: 2, label: t("result.feedbackGood"), icon: "🙂" },
    { value: 1, label: t("result.feedbackNeedsWork"), icon: "😐" },
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <button
        onClick={() => router.push("/dashboard")}
        className="mb-4 text-sm font-semibold text-[var(--muted)] transition-colors hover:text-[var(--foreground)]"
      >
        ← {t("result.backToDashboard")}
      </button>

      <motion.h1
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-4 text-2xl font-extrabold tracking-tight sm:text-3xl"
      >
        ✨ {result.title}
      </motion.h1>

      {/* Player — remount on seekTo change to jump via initial position */}
      <div key={playerKey}>
        <SeekablePlayer result={result} initialTime={seekTo} />
      </div>

      {/* Action buttons */}
      <div className="mt-5 flex flex-wrap gap-3">
        <Button
          onClick={() => downloadFile(result.download_url, `${result.title || "recap"}.mp4`, "video")}
        >
          ⬇️ {t("result.downloadVideo")}
        </Button>
        {result.subtitle_url && (
          <Button
            variant="secondary"
            onClick={() => downloadFile(result.subtitle_url!, `${result.title || "recap"}.srt`, "subtitle")}
          >
            💬 {t("result.downloadSubtitle")}
          </Button>
        )}
        <Button variant="secondary" onClick={share}>
          🔗 {t("result.share")}
        </Button>
      </div>

      {/* AI Summary */}
      <Card className="mt-6 p-6">
        <h2 className="mb-4 text-xl font-extrabold">📝 {t("result.summaryTitle")}</h2>
        <div className="rounded-xl border border-indigo-500/25 bg-gradient-to-br from-blue-600/10 to-violet-600/10 p-5">
          <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-indigo-500 dark:text-indigo-300">
            {t("result.shortSummary")}
          </h3>
          <p className="text-lg font-semibold leading-relaxed">{result.summary_short}</p>
        </div>
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-[var(--muted)]">
            {t("result.detailedSummary")}
          </h3>
          <p className="whitespace-pre-line leading-relaxed text-[var(--muted)]">
            {result.summary_long}
          </p>
        </div>
        {result.description && (
          <p className="mt-4 text-sm text-[var(--muted)]">{result.description}</p>
        )}
      </Card>

      {/* Key points */}
      {result.key_points.length > 0 && (
        <Card className="mt-6 p-6">
          <h2 className="mb-4 text-xl font-extrabold">📌 {t("result.keyPoints")}</h2>
          <ul className="space-y-2.5">
            {result.key_points.map((p, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -8 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="flex gap-3 rounded-xl bg-[var(--surface-2)]/60 p-3.5 text-sm leading-relaxed"
              >
                <span aria-hidden className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-600 text-xs font-bold text-white">
                  {i + 1}
                </span>
                {p}
              </motion.li>
            ))}
          </ul>
        </Card>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        {/* Timeline chapters */}
        <Card className="p-6">
          <h2 className="mb-4 text-xl font-extrabold">🗂️ {t("result.chapters")}</h2>
          {result.timeline.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">{t("result.noChapters")}</p>
          ) : (
            <ul className="space-y-1.5">
              {result.timeline.map((c, i) => (
                <li key={i}>
                  <button
                    onClick={() => jumpTo(c.start)}
                    className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left transition-colors hover:bg-[var(--surface-2)]"
                    aria-label={t("result.jumpTo", { time: formatDuration(c.start) })}
                  >
                    <span className="shrink-0 rounded-lg bg-indigo-500/15 px-2 py-1 text-xs font-bold tabular-nums text-indigo-600 dark:text-indigo-300">
                      {formatDuration(c.start)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{c.label}</span>
                    <span aria-hidden className="text-[var(--muted)]">▶</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Highlights */}
        <Card className="p-6">
          <h2 className="mb-4 text-xl font-extrabold">⭐ {t("result.highlights")}</h2>
          {result.highlights.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">{t("result.noHighlights")}</p>
          ) : (
            <ul className="space-y-1.5">
              {result.highlights.map((h, i) => (
                <li key={i}>
                  <button
                    onClick={() => jumpTo(h.start)}
                    className="flex w-full items-center gap-3 rounded-xl p-2.5 text-left transition-colors hover:bg-[var(--surface-2)]"
                    aria-label={t("result.jumpTo", { time: formatDuration(h.start) })}
                  >
                    <span className="shrink-0 rounded-lg bg-amber-500/15 px-2 py-1 text-xs font-bold tabular-nums text-amber-600 dark:text-amber-300">
                      {formatDuration(h.start)}–{formatDuration(h.end)}
                    </span>
                    <span className="min-w-0 flex-1 text-sm font-medium">
                      {t("result.highlights")} {i + 1}
                    </span>
                    <span className="shrink-0 text-xs tabular-nums text-[var(--muted)]">
                      {t("result.scoreLabel")}: {Math.round(h.score * 100)}%
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Transcript */}
      <Card className="mt-6 p-6">
        <h2 className="mb-4 text-xl font-extrabold">📄 {t("result.transcript")}</h2>
        {result.transcript.length === 0 ? (
          <EmptyState icon="📄" title={t("result.transcript")} description={t("result.noTranscript")} />
        ) : (
          <div className="max-h-96 space-y-1 overflow-y-auto pr-1">
            {result.transcript.map((cue, i) => (
              <button
                key={i}
                onClick={() => jumpTo(cue.start)}
                className="flex w-full gap-3 rounded-lg p-2 text-left text-sm transition-colors hover:bg-[var(--surface-2)]"
              >
                <span className="shrink-0 tabular-nums text-[var(--muted)]">
                  {formatDuration(cue.start)}
                </span>
                <span className="leading-relaxed">{cue.text}</span>
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Feedback */}
      <Card className="mt-6 p-6 text-center">
        {feedbackSent ? (
          <motion.p
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="py-4 text-lg font-bold text-emerald-600 dark:text-emerald-300"
          >
            ✅ {t("result.feedbackThanks")}
          </motion.p>
        ) : (
          <>
            <h2 className="text-xl font-extrabold">{t("result.feedbackTitle")}</h2>
            <div className="mt-4 flex justify-center gap-3">
              {ratingOptions.map((o) => (
                <motion.button
                  key={o.value}
                  whileTap={{ scale: 0.94 }}
                  onClick={() => setRating(o.value)}
                  aria-pressed={rating === o.value}
                  className={`flex min-w-28 flex-col items-center gap-1.5 rounded-2xl border p-4 transition-all ${
                    rating === o.value
                      ? "border-transparent bg-gradient-to-br from-blue-600 to-violet-600 text-white shadow-glow"
                      : "border-[var(--border)] hover:border-indigo-500/50"
                  }`}
                >
                  <span aria-hidden className="text-3xl">{o.icon}</span>
                  <span className="text-sm font-bold">{o.label}</span>
                </motion.button>
              ))}
            </div>
            <div className="mx-auto mt-4 max-w-md text-left">
              <label htmlFor="feedback-comment" className="label-text">
                {t("result.feedbackCommentLabel")} ({t("common.optional")})
              </label>
              <textarea
                id="feedback-comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t("result.feedbackPlaceholder")}
                rows={3}
                className="input-field resize-none"
              />
            </div>
            <Button
              className="mt-4"
              onClick={sendFeedback}
              loading={sendingFeedback}
              disabled={!rating}
            >
              {t("result.feedbackSubmit")}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}

/** Player wrapper that seeks to initialTime after metadata loads. */
function SeekablePlayer({
  result,
  initialTime,
}: {
  result: RecapResult;
  initialTime: number;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (initialTime > 0) {
      // Remount happened via key change; seek once the video element exists.
      const timer = setTimeout(() => setReady(true), 50);
      return () => clearTimeout(timer);
    }
    setReady(true);
  }, [initialTime]);

  return (
    <SeekInner
      result={result}
      initialTime={initialTime}
      ready={ready}
    />
  );
}

function SeekInner({
  result,
  initialTime,
  ready,
}: {
  result: RecapResult;
  initialTime: number;
  ready: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready || initialTime <= 0) return;
    const video = ref.current?.querySelector("video");
    if (!video) return;
    const onMeta = () => {
      video.currentTime = Math.min(initialTime, video.duration || initialTime);
      void video.play().catch(() => {});
    };
    if (video.readyState >= 1) onMeta();
    else video.addEventListener("loadedmetadata", onMeta, { once: true });
  }, [ready, initialTime]);

  return (
    <div ref={ref}>
      <VideoPlayer
        src={result.download_url}
        title={result.title}
        chapters={result.timeline}
        highlights={result.highlights}
        subtitleUrl={result.subtitle_url}
      />
    </div>
  );
}

export default function ResultPage({ params }: { params: { jobId: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <ResultContent jobId={params.jobId} />
      </AppShell>
    </RequireAuth>
  );
}
