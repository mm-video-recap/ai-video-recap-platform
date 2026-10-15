"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

export default function Footer() {
  const { t } = useT();
  const year = new Date().getFullYear();

  const product = [
    { href: "/upload", label: t("footer.links.upload") },
    { href: "/dashboard", label: t("footer.links.dashboard") },
    { href: "/admin", label: t("footer.links.admin") },
  ];
  const resources = [
    { href: "/contact", label: t("footer.links.help") },
    { href: "/contact", label: t("footer.links.contact") },
  ];
  const legal = [
    { href: "/privacy", label: t("footer.links.privacy") },
    { href: "/terms", label: t("footer.links.terms") },
    { href: "/content-policy", label: t("footer.links.contentPolicy") },
    { href: "/dmca", label: t("footer.links.dmca") },
  ];

  const Col = ({ title, links }: { title: string; links: { href: string; label: string }[] }) => (
    <div>
      <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--muted)]">
        {title}
      </h3>
      <ul className="space-y-2">
        {links.map((l) => (
          <li key={l.href + l.label}>
            <Link
              href={l.href}
              className="text-sm text-[var(--muted)] transition-colors hover:text-[var(--foreground)]"
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <footer className="border-t divider">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-lg text-white"
            >
              ▶
            </span>
            <span className="text-lg font-extrabold">
              AI <span className="text-gradient">Video Recap</span>
            </span>
          </div>
          <p className="mt-3 max-w-xs text-sm text-[var(--muted)]">{t("footer.tagline")}</p>
          <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-300">
            <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
            100% Free · Open Platform
          </div>
        </div>
        <Col title={t("footer.product")} links={product} />
        <Col title={t("footer.resources")} links={resources} />
        <Col title={t("footer.legal")} links={legal} />
      </div>
      <div className="border-t divider">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 py-5 text-xs text-[var(--muted)] sm:flex-row sm:px-6">
          <span>
            © {year} AI Video Recap. {t("footer.rights")}
          </span>
          <span>{t("meta.tagline")}</span>
        </div>
      </div>
    </footer>
  );
}
