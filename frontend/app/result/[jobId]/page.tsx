// Server component (no "use client"): Next.js forbids generateStaticParams
// in a "use client" file, so the page shell lives here while the
// interactive UI lives in ./content.tsx (a client component).
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import ResultContent from "./content";

// Static export: pre-render once for a placeholder jobId. The real jobId
// is read from the live URL at runtime via useParams() inside
// ResultContent, so any /result/<job-id> served via the host rewrite
// (public/_redirects) works.
export function generateStaticParams() {
  return [{ jobId: "placeholder" }];
}

export default function ResultPage() {
  return (
    <RequireAuth>
      <AppShell>
        <ResultContent />
      </AppShell>
    </RequireAuth>
  );
}
