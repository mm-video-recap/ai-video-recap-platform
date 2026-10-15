"use client";

import { useT } from "@/lib/i18n";
import type { Locale } from "@/lib/types";

/** 🇲🇲 / 🇬🇧 flag buttons to switch interface language. */
export default function LanguageToggle({ compact }: { compact?: boolean }) {
  const { locale, setLocale } = useT();

  const options: { value: Locale; flag: string; label: string }[] = [
    { value: "my", flag: "🇲🇲", label: "မြန်မာ" },
    { value: "en", flag: "🇬🇧", label: "English" },
  ];

  return (
    <div
      role="group"
      aria-label="Language"
      className={`flex items-center gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] ${compact ? "p-0.5" : "p-1"}`}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => setLocale(opt.value)}
          aria-pressed={locale === opt.value}
          title={opt.label}
          className={`flex items-center gap-1.5 rounded-lg font-medium transition-all ${
            compact ? "px-2 py-1 text-base" : "px-3 py-1.5 text-sm"
          } ${
            locale === opt.value
              ? "bg-gradient-to-r from-blue-600 to-violet-600 text-white shadow-glow"
              : "text-[var(--muted)] hover:text-[var(--foreground)]"
          }`}
        >
          <span aria-hidden>{opt.flag}</span>
          {!compact && <span>{opt.label}</span>}
        </button>
      ))}
    </div>
  );
}
