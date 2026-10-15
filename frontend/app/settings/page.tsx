"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { loadPreferences } from "@/lib/utils";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import LanguageToggle from "@/components/LanguageToggle";
import Card from "@/components/Card";
import Button from "@/components/Button";
import type { RecapStyle } from "@/lib/types";

function SettingsContent() {
  const { t } = useT();
  const { user } = useAuth();
  const { toast } = useToast();
  const [summaryStyle, setSummaryStyle] = useState<RecapStyle>("detailed");
  const [defaultLanguage, setDefaultLanguage] = useState<"my" | "en">("my");

  useEffect(() => {
    const p = loadPreferences();
    if (["concise", "detailed", "highlights"].includes(p.summaryStyle)) {
      setSummaryStyle(p.summaryStyle as RecapStyle);
    }
    if (p.defaultLanguage === "en" || p.defaultLanguage === "my") {
      setDefaultLanguage(p.defaultLanguage);
    }
  }, []);

  const save = () => {
    try {
      window.localStorage.setItem(
        "recap_prefs",
        JSON.stringify({ summaryStyle, defaultLanguage })
      );
      toast(t("settings.saved"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    }
  };

  const segmented = (
    value: string,
    onChange: (v: string) => void,
    options: { value: string; label: string }[]
  ) => (
    <div role="radiogroup" className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-xl border px-4 py-2.5 text-sm font-semibold transition-all ${
            value === o.value
              ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-600 text-white shadow-glow"
              : "border-[var(--border)] bg-[var(--surface)] hover:border-indigo-500/50"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          {t("settings.title")}
        </h1>
        <p className="mt-1 text-[var(--muted)]">{t("settings.subtitle")}</p>
      </motion.div>

      <div className="mt-6 space-y-5">
        <Card className="p-6">
          <h2 className="text-lg font-bold">{t("settings.languageTitle")}</h2>
          <p className="mb-4 mt-1 text-sm text-[var(--muted)]">{t("settings.languageDesc")}</p>
          <LanguageToggle />
        </Card>

        <Card className="p-6">
          <h2 className="text-lg font-bold">{t("settings.prefsTitle")}</h2>
          <p className="mb-5 mt-1 text-sm text-[var(--muted)]">{t("settings.prefsDesc")}</p>
          <div className="space-y-5">
            <div>
              <span className="label-text">{t("settings.summaryStyleLabel")}</span>
              {segmented(summaryStyle, (v) => setSummaryStyle(v as RecapStyle), [
                { value: "concise", label: t("upload.styles.concise") },
                { value: "detailed", label: t("upload.styles.detailed") },
                { value: "highlights", label: t("upload.styles.highlights") },
              ])}
            </div>
            <div>
              <span className="label-text">{t("settings.defaultLangLabel")}</span>
              {segmented(defaultLanguage, (v) => setDefaultLanguage(v as "my" | "en"), [
                { value: "my", label: `🇲🇲 ${t("upload.langMy")}` },
                { value: "en", label: `🇬🇧 ${t("upload.langEn")}` },
              ])}
            </div>
            <Button onClick={save}>💾 {t("common.save")}</Button>
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-lg font-bold">{t("settings.accountTitle")}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {t("settings.accountDesc", { email: user?.email ?? "" })}
          </p>
        </Card>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <RequireAuth>
      <AppShell>
        <SettingsContent />
      </AppShell>
    </RequireAuth>
  );
}
