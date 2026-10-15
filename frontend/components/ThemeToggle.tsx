"use client";

import { useTheme } from "@/components/ThemeProvider";
import { useT } from "@/lib/i18n";

export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const { t } = useT();
  const isDark = theme === "dark";

  return (
    <button
      onClick={toggle}
      aria-label={isDark ? t("themeToggle.switchToLight") : t("themeToggle.switchToDark")}
      title={isDark ? t("themeToggle.light") : t("themeToggle.dark")}
      className="flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface)] text-lg transition-all hover:border-indigo-500/50 hover:shadow-glow"
    >
      <span aria-hidden className="transition-transform duration-300">
        {isDark ? "🌙" : "☀️"}
      </span>
    </button>
  );
}
