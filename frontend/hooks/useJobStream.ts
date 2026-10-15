"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getJob, streamUrl } from "@/lib/api";
import { normalizeStage, STAGE_ORDER } from "@/lib/utils";
import type { StreamEvent } from "@/lib/types";

export interface JobStreamState {
  stage: string;
  progress: number;
  message: string;
  status: "queued" | "processing" | "completed" | "failed";
  error: string | null;
  connected: boolean;
}

/**
 * Live job updates via SSE (EventSource with ?token=), falling back to polling.
 */
export function useJobStream(jobId: string | null): JobStreamState {
  const { getAccessToken } = useAuth();
  const [state, setState] = useState<JobStreamState>({
    stage: "upload",
    progress: 0,
    message: "",
    status: "queued",
    error: null,
    connected: false,
  });
  const stopPolling = useRef(false);

  useEffect(() => {
    if (!jobId) return;
    stopPolling.current = false;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const applyEvent = (ev: StreamEvent) => {
      setState((prev) => ({
        ...prev,
        stage: normalizeStage(ev.stage),
        progress: Math.max(0, Math.min(100, ev.progress ?? prev.progress)),
        message: ev.message ?? prev.message,
        // Backend SSE payloads carry the job status; stage alone is not
        // enough (e.g. stage "gone" on failure, "done" on completion).
        status:
          ev.status === "queued" ||
          ev.status === "processing" ||
          ev.status === "completed" ||
          ev.status === "failed"
            ? ev.status
            : prev.status,
      }));
    };

    const pollOnce = async (token: string | null) => {
      try {
        const job = await getJob(jobId, token);
        setState((prev) => ({
          ...prev,
          stage: normalizeStage(job.stage),
          progress: Math.max(0, Math.min(100, job.progress ?? 0)),
          status: (job.status as JobStreamState["status"]) || prev.status,
          error: job.error ?? null,
        }));
        const st = job.status;
        if (st === "completed" || st === "failed") {
          stopPolling.current = true;
          if (pollTimer) clearInterval(pollTimer);
          if (es) es.close();
        }
      } catch {
        /* keep last state */
      }
    };

    const startPolling = (token: string | null) => {
      void pollOnce(token);
      pollTimer = setInterval(() => {
        if (!stopPolling.current) void pollOnce(token);
      }, 3000);
    };

    void (async () => {
      const token = await getAccessToken();
      if (stopPolling.current) return;
      try {
        if (token) {
          es = new EventSource(streamUrl(jobId, token));
          es.onopen = () =>
            setState((p) => ({ ...p, connected: true, status: "processing" }));
          // Backend emits NAMED `event: progress` SSE events — onmessage only
          // fires for unnamed events, so subscribe to the named event explicitly.
          const handleMessage = (msg: MessageEvent) => {
            try {
              const ev = JSON.parse(msg.data) as StreamEvent;
              applyEvent(ev);
              const st = normalizeStage(ev.stage);
              if (st === "completed" || ev.status === "completed") {
                setState((p) => ({ ...p, status: "completed", progress: 100 }));
                es?.close();
                stopPolling.current = true;
                if (pollTimer) clearInterval(pollTimer);
              } else if (ev.status === "failed") {
                setState((p) => ({ ...p, status: "failed" }));
                es?.close();
                stopPolling.current = true;
                if (pollTimer) clearInterval(pollTimer);
              }
            } catch {
              /* ignore malformed events */
            }
          };
          es.addEventListener("progress", handleMessage as EventListener);
          // Fallback: also handle unnamed events if the server ever sends them.
          es.onmessage = handleMessage;
          // Backend ends the stream with `event: timeout` after ~115s without
          // a terminal state — fall back to polling instead of hanging.
          es.addEventListener("timeout", () => {
            es?.close();
            if (!stopPolling.current) startPolling(token);
          });
          es.onerror = () => {
            es?.close();
            // SSE failed — fall back to polling.
            if (!stopPolling.current) startPolling(token);
          };
        } else {
          startPolling(null);
        }
      } catch {
        startPolling(token);
      }
    })();

    return () => {
      stopPolling.current = true;
      if (pollTimer) clearInterval(pollTimer);
      if (es) es.close();
    };
  }, [jobId, getAccessToken]);

  return state;
}

export { STAGE_ORDER };
