"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

/** Redirects to /login when there is no session; renders children when authed. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div
          aria-hidden
          className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-500/30 border-t-indigo-500"
        />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return <>{children}</>;
}
