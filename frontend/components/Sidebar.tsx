"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

const ICONS: Record<string, string> = {
  dashboard: "📊",
  myVideos: "🎬",
  upload: "⬆️",
  results: "✨",
  settings: "⚙️",
  help: "❓",
  admin: "🛡️",
};

export default function Sidebar() {
  const { t } = useT();
  const { profile } = useAuth();
  const pathname = usePathname();

  const items = [
    { key: "dashboard", href: "/dashboard" },
    { key: "myVideos", href: "/dashboard/videos" },
    { key: "upload", href: "/upload" },
    { key: "results", href: "/dashboard/results" },
    { key: "settings", href: "/settings" },
    { key: "help", href: "/contact" },
  ];
  if (profile?.is_admin) items.push({ key: "admin", href: "/admin" });

  return (
    <aside
      aria-label="Sidebar"
      className="sticky top-16 hidden h-[calc(100vh-4rem)] w-60 shrink-0 flex-col gap-1 overflow-y-auto border-r divider p-4 md:flex"
    >
      {items.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all ${
              active
                ? "bg-gradient-to-r from-blue-600/20 to-violet-600/20 text-[var(--foreground)] shadow-[inset_0_0_0_1px_rgba(99,102,241,0.35)]"
                : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
            }`}
          >
            <span aria-hidden className="text-lg">
              {ICONS[item.key] ?? "•"}
            </span>
            {t(`sidebar.${item.key}`)}
          </Link>
        );
      })}
      <div className="mt-auto rounded-xl border border-indigo-500/25 bg-gradient-to-br from-blue-600/10 to-violet-600/10 p-4">
        <p className="text-sm font-bold">🚀 {t("meta.appName")}</p>
        <p className="mt-1 text-xs text-[var(--muted)]">{t("footer.tagline")}</p>
        <Link
          href="/upload"
          className="mt-3 inline-block rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-3 py-1.5 text-xs font-bold text-white"
        >
          {t("sidebar.upload")} →
        </Link>
      </div>
    </aside>
  );
}
