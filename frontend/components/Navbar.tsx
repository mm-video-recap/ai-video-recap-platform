"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import LanguageToggle from "@/components/LanguageToggle";
import ThemeToggle from "@/components/ThemeToggle";
import Dropdown, { DropdownItem } from "@/components/Dropdown";
import Button from "@/components/Button";

function Logo() {
  const { t } = useT();
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label={t("meta.appName")}>
      <span
        aria-hidden
        className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-lg text-white shadow-glow"
      >
        ▶
      </span>
      <span className="text-lg font-extrabold tracking-tight">
        AI <span className="text-gradient">Video Recap</span>
      </span>
    </Link>
  );
}

export default function Navbar() {
  const { t } = useT();
  const { user, profile, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  const links = [
    { href: "/#features", label: t("nav.features") },
    { href: "/#how-it-works", label: t("nav.howItWorks") },
    { href: "/#technology", label: t("nav.technology") },
    { href: "/#faq", label: t("nav.faq") },
  ];

  const isAppPage =
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/upload") ||
    pathname.startsWith("/processing") ||
    pathname.startsWith("/result") ||
    pathname.startsWith("/admin") ||
    pathname.startsWith("/settings");

  return (
    <header className="sticky top-0 z-40 border-b divider bg-[var(--background)]/80 backdrop-blur-xl">
      <nav
        aria-label="Main"
        className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6"
      >
        <Logo />

        {!isAppPage && (
          <div className="hidden items-center gap-1 lg:flex">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="rounded-lg px-3 py-2 text-sm font-medium text-[var(--muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
              >
                {l.label}
              </Link>
            ))}
          </div>
        )}

        <div className="hidden items-center gap-2 sm:flex">
          <LanguageToggle compact />
          <ThemeToggle />
          {user ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => router.push("/dashboard")}
              >
                {t("nav.dashboard")}
              </Button>
              <Dropdown
                ariaLabel={t("nav.dashboard")}
                label={
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-600 text-sm font-bold text-white">
                    {(profile?.display_name || user.email || "U")[0].toUpperCase()}
                  </span>
                }
              >
                <div className="px-3 py-2 text-xs text-[var(--muted)]">
                  {profile?.display_name || user.email}
                </div>
                <DropdownItem onClick={() => router.push("/settings")}>
                  ⚙️ {t("sidebar.settings")}
                </DropdownItem>
                {profile?.is_admin && (
                  <DropdownItem onClick={() => router.push("/admin")}>
                    🛡️ {t("sidebar.admin")}
                  </DropdownItem>
                )}
                <DropdownItem
                  danger
                  onClick={() => {
                    void signOut().then(() => router.push("/"));
                  }}
                >
                  ⎋ {t("nav.logout")}
                </DropdownItem>
              </Dropdown>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-[var(--surface-2)]"
              >
                {t("nav.login")}
              </Link>
              <Button size="sm" onClick={() => router.push("/login")}>
                {t("nav.getStarted")}
              </Button>
            </>
          )}
        </div>

        {/* Mobile menu button */}
        <button
          className="rounded-xl p-2 sm:hidden"
          aria-label="Menu"
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((o) => !o)}
        >
          <span aria-hidden className="text-xl">{mobileOpen ? "✕" : "☰"}</span>
        </button>
      </nav>

      {/* Mobile panel */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="border-t divider px-4 py-4 sm:hidden"
        >
          <div className="flex flex-col gap-1">
            {!isAppPage &&
              links.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg px-3 py-2.5 text-sm font-medium hover:bg-[var(--surface-2)]"
                >
                  {l.label}
                </Link>
              ))}
            <div className="mt-2 flex items-center gap-2">
              <LanguageToggle compact />
              <ThemeToggle />
            </div>
            <div className="mt-3 flex gap-2">
              {user ? (
                <>
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => router.push("/dashboard")}
                  >
                    {t("nav.dashboard")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      void signOut().then(() => router.push("/"));
                    }}
                  >
                    {t("nav.logout")}
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => router.push("/login")}
                  >
                    {t("nav.login")}
                  </Button>
                  <Button className="flex-1" onClick={() => router.push("/login")}>
                    {t("nav.getStarted")}
                  </Button>
                </>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </header>
  );
}
