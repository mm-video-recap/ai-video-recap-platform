"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/lib/i18n";

/** Mobile bottom navigation (sidebar collapses on small screens). */
export default function BottomNav() {
  const { t } = useT();
  const pathname = usePathname();

  const items = [
    { key: "dashboard", href: "/dashboard", icon: "📊" },
    { key: "myVideos", href: "/dashboard/videos", icon: "🎬" },
    { key: "upload", href: "/upload", icon: "⬆️" },
    { key: "results", href: "/dashboard/results", icon: "✨" },
    { key: "settings", href: "/settings", icon: "⚙️" },
  ];

  return (
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-40 border-t divider bg-[var(--background)]/90 backdrop-blur-xl md:hidden"
    >
      <div className="grid grid-cols-5 px-2 pb-[env(safe-area-inset-bottom)]">
        {items.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.key}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl text-[11px] font-medium transition-colors ${
                active
                  ? "text-indigo-500 dark:text-indigo-300"
                  : "text-[var(--muted)]"
              }`}
            >
              <span aria-hidden className={`text-xl ${active ? "scale-110" : ""}`}>
                {item.icon}
              </span>
              {t(`sidebar.${item.key}`)}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
