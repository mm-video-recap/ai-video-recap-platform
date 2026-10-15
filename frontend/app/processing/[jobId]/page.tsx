"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n";
import { useJobStream } from "@/hooks/useJobStream";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import ProcessingSteps from "@/components/ProcessingSteps";
import Card from "@/components/Card";
import Button from "@/components/Button";
import type { StageKey } from "@/lib/utils";

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function ProcessingContent({ jobId }: { jobId: string }) {
  const { t } = useT();
  const router = useRouter();
  const { stage, progress, message, status, error } = useJobStream(jobId);
  const [elapsed, setElapsed] = useState(0);
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - start), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (status === "completed" && !redirecting) {
      setRedirecting(true);
      const timer = setTimeout(() => router.push(`/result/${jobId}`), 1800);
      return () => clearTimeout(timer);
    }
  }, [status, redirecting, router, jobId]);

  const failed = status === "failed";

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 text-center">
        <div
          aria-hidden
          className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-4xl text-white shadow-glow-lg"
        >
          <span className={failed ? "" : "animate-spin-slow"}>{failed ? "⚠️" : "🧠"}</span>
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          {failed ? t("processing.failedTitle") : t("processing.title")}
        </h1>
        <p className="mt-1.5 text-[var(--muted)]">
          {failed ? t("processing.failedDesc") : t("processing.subtitle")}
        </p>
        <p className="mt-2 text-sm tabular-nums text-[var(--muted)]">
          ⏱ {t("processing.elapsed")}: {formatElapsed(elapsed)}
        </p>
      </div>

      {failed ? (
        <Card className="border-red-500/30 p-8 text-center">
          <p role="alert" className="mx-auto max-w-md text-sm text-[var(--muted)]">
            {error || t("errors.generic")}
          </p>
          <p className="mx-auto mt-3 max-w-md text-sm text-[var(--muted)]">
            {t("processing.retryHint")}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={() => router.push("/upload")}>
              {t("common.retry")}
            </Button>
            <Button variant="secondary" onClick={() => router.push("/dashboard")}>
              {t("processing.backToDashboard")}
            </Button>
          </div>
        </Card>
      ) : redirecting ? (
        <Card className="p-10 text-center">
          <div aria-hidden className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15 text-3xl">
            ✅
          </div>
          <p className="font-bold text-emerald-600 dark:text-emerald-300">
            {t("processing.redirecting")}
          </p>
        </Card>
      ) : (
        <>
          <ProcessingSteps
            currentStage={stage as StageKey}
            progress={progress}
            message={message}
          />
          {message && (
            <Card className="mt-4 p-4">
              <p className="text-sm">
                <span className="font-bold">📡 {t("processing.liveLog")}: </span>
                <span className="text-[var(--muted)]">{message}</span>
              </p>
            </Card>
          )}
          <div className="mt-6 text-center">
            <Button variant="ghost" onClick={() => router.push("/dashboard")}>
              ← {t("processing.backToDashboard")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export default function ProcessingPage({ params }: { params: { jobId: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <ProcessingContent jobId={params.jobId} />
      </AppShell>
    </RequireAuth>
  );
}
