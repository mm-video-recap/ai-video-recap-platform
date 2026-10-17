"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { loadPreferences, loadQuotaWarningEnabled, loadUserKeys, saveQuotaWarningEnabled, saveUserKeys } from "@/lib/utils";
import { verifyApiKey } from "@/lib/api";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import LanguageToggle from "@/components/LanguageToggle";
import Card from "@/components/Card";
import Button from "@/components/Button";

function SettingsContent() {
  const { t } = useT();
  const { user, getAccessToken } = useAuth();
  const { toast } = useToast();
  const [defaultLanguage, setDefaultLanguage] = useState<"my" | "en">("my");
  const [quotaWarning, setQuotaWarning] = useState(true);
  const [geminiKey, setGeminiKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [showGemini, setShowGemini] = useState(false);
  const [showGroq, setShowGroq] = useState(false);
  type VerifyState = "idle" | "loading" | "ok" | "invalid" | "quota" | "error";
  const [verifyGemini, setVerifyGemini] = useState<VerifyState>("idle");
  const [verifyGroq, setVerifyGroq] = useState<VerifyState>("idle");

  useEffect(() => {
    const p = loadPreferences();
    if (p.defaultLanguage === "en" || p.defaultLanguage === "my") {
      setDefaultLanguage(p.defaultLanguage);
    }
    const uk = loadUserKeys();
    setGeminiKey(uk.geminiKey);
    setGroqKey(uk.groqKey);
    setQuotaWarning(loadQuotaWarningEnabled());
  }, []);

  const save = () => {
    try {
      window.localStorage.setItem(
        "recap_prefs",
        JSON.stringify({ defaultLanguage })
      );
      saveQuotaWarningEnabled(quotaWarning);
      saveUserKeys({ geminiKey, groqKey });
      toast(t("settings.saved"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    }
  };

  // Verify ONE key against its provider (key sent in the JSON body,
  // never stored, never logged). Works on the current field value
  // even before Save.
  const verifyOne = async (
    provider: "gemini" | "groq",
    key: string,
    setState: (s: VerifyState) => void
  ) => {
    if (!key.trim()) {
      toast(t("settings.keyEmpty"), "error");
      return;
    }
    setState("loading");
    try {
      const token = await getAccessToken();
      const res = await verifyApiKey(token, provider, key.trim());
      if (res.valid && res.reason === "ok") setState("ok");
      else if (res.valid && res.reason === "quota") setState("quota");
      else if (!res.valid && res.reason === "invalid") setState("invalid");
      else setState("error");
    } catch {
      setState("error");
    }
  };

  // Delete ONE key: clear the field AND the browser-saved copy at once.
  const deleteOne = (
    provider: "gemini" | "groq",
    setValue: (v: string) => void,
    setState: (s: VerifyState) => void
  ) => {
    setValue("");
    setState("idle");
    const next = {
      geminiKey: provider === "gemini" ? "" : geminiKey,
      groqKey: provider === "groq" ? "" : groqKey,
    };
    saveUserKeys(next);
    toast(t("settings.keyDeleted"), "success");
  };

  const verifyLabel = (s: VerifyState) => {
    if (s === "loading") return t("settings.keyVerifying");
    if (s === "ok") return `✅ ${t("settings.keyValid")}`;
    if (s === "quota") return `⚠️ ${t("settings.keyQuota")}`;
    if (s === "invalid") return `❌ ${t("settings.keyInvalid")}`;
    if (s === "error") return `❌ ${t("settings.keyError")}`;
    return "";
  };

  // One key field with its own three icons: show/hide, verify, delete.
  const keyField = (
    label: string,
    placeholder: string,
    value: string,
    onChange: (v: string) => void,
    shown: boolean,
    onToggleShow: () => void,
    verifyState: VerifyState,
    onVerify: () => void,
    onDelete: () => void
  ) => (
    <div>
      <span className="label-text">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type={shown ? "text" : "password"}
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm outline-none focus:border-indigo-500"
        />
        <button
          type="button"
          onClick={onToggleShow}
          title={shown ? t("settings.keyHide") : t("settings.keyShow")}
          aria-label={shown ? t("settings.keyHide") : t("settings.keyShow")}
          className="shrink-0 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-base"
        >
          {shown ? "🙈" : "👁️"}
        </button>
        <button
          type="button"
          onClick={onVerify}
          disabled={verifyState === "loading"}
          title={t("settings.keyVerify")}
          aria-label={t("settings.keyVerify")}
          className="shrink-0 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-base disabled:opacity-50"
        >
          ✓
        </button>
        <button
          type="button"
          onClick={onDelete}
          title={t("settings.keyDelete")}
          aria-label={t("settings.keyDelete")}
          className="shrink-0 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-base"
        >
          🗑️
        </button>
      </div>
      {verifyState !== "idle" && (
        <p className="mt-1.5 text-xs text-[var(--muted)]">{verifyLabel(verifyState)}</p>
      )}
    </div>
  );

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
              <span className="label-text">{t("settings.defaultLangLabel")}</span>
              {segmented(defaultLanguage, (v) => setDefaultLanguage(v as "my" | "en"), [
                { value: "my", label: `🇲🇲 ${t("upload.langMy")}` },
                { value: "en", label: `🇬🇧 ${t("upload.langEn")}` },
              ])}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={quotaWarning}
              onClick={() => setQuotaWarning((v) => !v)}
              className="flex w-full items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-left"
            >
              <span>
                <span className="block text-sm font-semibold">{t("settings.quotaWarningLabel")}</span>
                <span className="mt-0.5 block text-xs text-[var(--muted)]">{t("settings.quotaWarningDesc")}</span>
              </span>
              <span
                aria-hidden
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                  quotaWarning ? "bg-gradient-to-r from-blue-600 to-violet-600" : "bg-[var(--border)]"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
                    quotaWarning ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </span>
            </button>
            <Button onClick={save}>💾 {t("common.save")}</Button>
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-lg font-bold">{t("settings.aiKeysTitle")}</h2>
          <p className="mb-5 mt-1 text-sm text-[var(--muted)]">{t("settings.aiKeysDesc")}</p>
          <div className="space-y-5">
            {keyField(
              t("settings.aiKeysGemini"),
              t("settings.aiKeysGeminiPlaceholder"),
              geminiKey,
              (v) => { setGeminiKey(v); setVerifyGemini("idle"); },
              showGemini,
              () => setShowGemini((s) => !s),
              verifyGemini,
              () => verifyOne("gemini", geminiKey, setVerifyGemini),
              () => deleteOne("gemini", setGeminiKey, setVerifyGemini)
            )}
            {keyField(
              t("settings.aiKeysGroq"),
              t("settings.aiKeysGroqPlaceholder"),
              groqKey,
              (v) => { setGroqKey(v); setVerifyGroq("idle"); },
              showGroq,
              () => setShowGroq((s) => !s),
              verifyGroq,
              () => verifyOne("groq", groqKey, setVerifyGroq),
              () => deleteOne("groq", setGroqKey, setVerifyGroq)
            )}
            <p className="text-xs text-[var(--muted)]">{t("settings.aiKeysHint")}</p>
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
