"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

/**
 * Resolve the [jobId] route param from the LIVE URL at runtime.
 *
 * In a static export, useParams() returns the BUILD-TIME param
 * ("placeholder" from generateStaticParams), NOT the segment of the
 * URL the browser actually shows — the host rewrite serves the
 * placeholder HTML for any /processing/<id> or /result/<id>. Reading
 * window.location.pathname after mount gives the real id.
 *
 * Returns null until the real id is known, so callers never poll
 * /api/jobs/placeholder (live incident 2026-10-16: the processing
 * page polled the literal placeholder id and got 404 forever).
 */
export function useLiveJobId(): string | null {
  const params = useParams();
  const staticId = typeof params.jobId === "string" ? params.jobId : null;
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    const seg = window.location.pathname.split("/").filter(Boolean).pop() ?? null;
    setJobId(seg && seg !== "placeholder" ? seg : staticId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return jobId;
}
