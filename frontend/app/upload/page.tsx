"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { uploadVideo } from "@/lib/api";
import {
  ACCEPTED_VIDEO_TYPES,
  MAX_UPLOAD_BYTES,
  estimateMinutes,
  formatBytes,
  formatDuration,
  getExtension,
  loadPreferences,
  loadUserKeys,
  loadVoicePrefs,
  saveVoicePrefs,
  type VoicePrefs,
} from "@/lib/utils";
import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import FileUploader from "@/components/FileUploader";
import ProgressBar from "@/components/ProgressBar";
import Button from "@/components/Button";
import Card from "@/components/Card";

type Lang = "my" | "en" | "none";

function UploadContent() {
  const { t } = useT();
  const { getAccessToken, profile } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Key gate: only the owner account may use the server keys. Everyone
  // else needs BOTH their own Gemini + Groq keys saved in Settings.
  const savedKeys = useMemo(() => loadUserKeys(), []);
  const keysMissing =
    profile !== null &&
    !profile.is_owner &&
    (!savedKeys.geminiKey || !savedKeys.groqKey);

  const prefs = useMemo(() => loadPreferences(), []);
  const [summaryLang, setSummaryLang] = useState<"my" | "en">(prefs.defaultLanguage as "my" | "en");
  const [subtitleLang, setSubtitleLang] = useState<Lang>(prefs.defaultLanguage as "my" | "en");
  const [introEnabled, setIntroEnabled] = useState(true);
  const [outroEnabled, setOutroEnabled] = useState(true);
  const [introFile, setIntroFile] = useState<File | null>(null);
  const [outroFile, setOutroFile] = useState<File | null>(null);
  const [voice, setVoice] = useState<VoicePrefs>(() => loadVoicePrefs());

  const updateVoice = (patch: Partial<VoicePrefs>) => {
    setVoice((prev) => {
      const next = { ...prev, ...patch };
      // Edge voices are Thiha/Nilar; Gemini voices are the 8 named ones.
      if (patch.ttsProvider === "edge" && !["thiha", "nilar"].includes(next.ttsVoice)) {
        next.ttsVoice = "thiha";
      }
      if (patch.ttsProvider === "gemini" && ["thiha", "nilar"].includes(next.ttsVoice)) {
        next.ttsVoice = "Kore";
      }
      saveVoicePrefs(next);
      return next;
    });
  };

  // Read video duration from file metadata for the time estimate.
  useEffect(() => {
    if (!file) {
      setDuration(0);
      return;
    }
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      setDuration(video.duration || 0);
      URL.revokeObjectURL(url);
    };
    video.onerror = () => URL.revokeObjectURL(url);
    video.src = url;
  }, [file]);

  const handleFile = (f: File | null) => {
    setError(null);
    if (!f) {
      setFile(null);
      return;
    }
    const ext = getExtension(f.name);
    if (!ACCEPTED_VIDEO_TYPES.includes(ext)) {
      setError(t("upload.errors.invalidType"));
      return;
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setError(t("upload.errors.tooLarge"));
      return;
    }
    setFile(f);
  };

  const startUpload = async () => {
    if (!file) {
      setError(t("upload.errors.noFile"));
      return;
    }
    if (keysMissing) {
      setError(t("upload.keysRequired"));
      return;
    }
    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const token = await getAccessToken();
      if (!token) {
        setError(t("upload.errors.notLoggedIn"));
        setUploading(false);
        return;
      }
      const result = await uploadVideo(
        file,
        token,
        (pct) => setProgress(pct),
        {
          // output_lang / subtitle_language are sent as query params
          // (see lib/api.ts) and persisted on the backend Job.
          output_lang: summaryLang,
          subtitle_language: subtitleLang,
          intro_enabled: String(introEnabled),
          outro_enabled: String(outroEnabled),
          // Uploaded intro/outro videos (form fields): the final recap
          // is intro video + recap clips + outro video. No file means
          // the default text card. Only sent when the toggle is on.
          ...(introEnabled && introFile ? { intro_file: introFile } : {}),
          ...(outroEnabled && outroFile ? { outro_file: outroFile } : {}),
          // Voiceover (TTS narration) prefs from this page.
          voice_mode: voice.voiceMode,
          tts_provider: voice.ttsProvider,
          tts_voice: voice.ttsVoice,
          tts_rate: String(voice.ttsRate),
          tts_pitch: String(voice.ttsPitch),
          // Per-user AI keys from Settings (one entry for everything):
          // form fields, never in the URL. When set, this job spends
          // the user's own quota.
          ...(() => {
            const uk = loadUserKeys();
            return {
              ...(uk.geminiKey ? { gemini_key: uk.geminiKey } : {}),
              ...(uk.groqKey ? { groq_key: uk.groqKey } : {}),
            };
          })(),
        }
      );
      toast(t("upload.success"), "success");
      router.push(`/processing/${result.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("upload.errors.uploadFailed"));
      setUploading(false);
    }
  };

  const estMinutes = estimateMinutes(duration);

  const segmented = (value: string, onChange: (v: string) => void, options: { value: string; label: string }[]) => (
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

  const toggleRow = (label: string, value: boolean, onChange: (v: boolean) => void) => (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className="flex w-full items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-left"
    >
      <span className="text-sm font-semibold">{label}</span>
      <span
        aria-hidden
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
          value ? "bg-gradient-to-r from-blue-600 to-violet-600" : "bg-[var(--border)]"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
            value ? "left-[22px]" : "left-0.5"
          }`}
        />
      </span>
    </button>
  );

  return (
    <div className="mx-auto max-w-3xl">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{t("upload.title")}</h1>
        <p className="mt-1 text-[var(--muted)]">{t("upload.subtitle")}</p>
      </motion.div>

      <div className="mt-6 space-y-6">
        {keysMissing && (
          <div className="rounded-xl border border-amber-500/50 bg-amber-500/10 px-4 py-3 text-sm">
            ⚠️ {t("upload.keysRequired")}{" "}
            <button
              type="button"
              onClick={() => router.push("/settings")}
              className="font-semibold underline"
            >
              {t("upload.keysRequiredCta")}
            </button>
          </div>
        )}
        <FileUploader file={file} onFile={handleFile} error={error} />

        {file && !uploading && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-bold">{t("upload.settingsTitle")}</h2>
              <div className="space-y-5">
                <div>
                  <span className="label-text">{t("upload.summaryLang")}</span>
                  {segmented(summaryLang, (v) => setSummaryLang(v as "my" | "en"), [
                    { value: "my", label: `🇲🇲 ${t("upload.langMy")}` },
                    { value: "en", label: `🇬🇧 ${t("upload.langEn")}` },
                  ])}
                </div>
                <div>
                  <span className="label-text">{t("upload.subtitleLang")}</span>
                  {segmented(subtitleLang, (v) => setSubtitleLang(v as Lang), [
                    { value: "my", label: `🇲🇲 ${t("upload.langMy")}` },
                    { value: "en", label: `🇬🇧 ${t("upload.langEn")}` },
                    { value: "none", label: t("upload.langNone") },
                  ])}
                </div>
                <div>
                  <span className="label-text">{t("upload.introOutro")}</span>
                  <div className="space-y-3">
                    {toggleRow(t("upload.introEnabled"), introEnabled, setIntroEnabled)}
                    {introEnabled && (
                      <div className="space-y-1.5">
                        <label className="block cursor-pointer rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm">
                          <input
                            type="file"
                            accept="video/*"
                            className="hidden"
                            aria-label={t("upload.introVideo")}
                            onChange={(e) => setIntroFile(e.target.files?.[0] ?? null)}
                          />
                          {introFile ? `🎬 ${introFile.name}` : t("upload.introVideoPlaceholder")}
                        </label>
                        {introFile && (
                          <button
                            type="button"
                            onClick={() => setIntroFile(null)}
                            className="text-xs text-red-500 underline"
                          >
                            {t("upload.remove")}
                          </button>
                        )}
                      </div>
                    )}
                    {toggleRow(t("upload.outroEnabled"), outroEnabled, setOutroEnabled)}
                    {outroEnabled && (
                      <div className="space-y-1.5">
                        <label className="block cursor-pointer rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm">
                          <input
                            type="file"
                            accept="video/*"
                            className="hidden"
                            aria-label={t("upload.outroVideo")}
                            onChange={(e) => setOutroFile(e.target.files?.[0] ?? null)}
                          />
                          {outroFile ? `🎬 ${outroFile.name}` : t("upload.outroVideoPlaceholder")}
                        </label>
                        {outroFile && (
                          <button
                            type="button"
                            onClick={() => setOutroFile(null)}
                            className="text-xs text-red-500 underline"
                          >
                            {t("upload.remove")}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                <div>
                  <span className="label-text">{t("upload.voiceTitle")}</span>
                  {segmented(voice.voiceMode, (v) => updateVoice({ voiceMode: v as "original" | "tts" }), [
                    { value: "original", label: t("upload.voiceOriginal") },
                    { value: "tts", label: t("upload.voiceTts") },
                  ])}
                  {voice.voiceMode === "tts" && (
                    <div className="mt-3 space-y-3">
                      {segmented(voice.ttsProvider, (v) => updateVoice({ ttsProvider: v as "edge" | "gemini" }), [
                        { value: "edge", label: "Edge TTS" },
                        { value: "gemini", label: "Gemini" },
                      ])}
                      <div>
                        <span className="label-text">{t("upload.ttsVoice")}</span>
                        <select
                          value={voice.ttsVoice}
                          onChange={(e) => updateVoice({ ttsVoice: e.target.value })}
                          className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm"
                        >
                          {voice.ttsProvider === "edge" ? (
                            <>
                              <option value="thiha">{t("upload.voiceThiha")}</option>
                              <option value="nilar">{t("upload.voiceNilar")}</option>
                            </>
                          ) : (
                            ["Kore", "Charon", "Zephyr", "Puck", "Leda", "Fenrir", "Callirrhoe", "Autonoe"].map((v) => (
                              <option key={v} value={v}>{v}</option>
                            ))
                          )}
                        </select>
                      </div>
                      <div>
                        <span className="label-text">{t("upload.ttsRate", { rate: voice.ttsRate.toFixed(2) })}</span>
                        <input
                          type="range" min={0.8} max={1.3} step={0.05} value={voice.ttsRate}
                          onChange={(e) => updateVoice({ ttsRate: Number(e.target.value) })}
                          className="w-full"
                          aria-label={t("upload.ttsRate", { rate: voice.ttsRate.toFixed(2) })}
                        />
                      </div>
                      <div>
                        <span className="label-text">{t("upload.ttsPitch", { pitch: voice.ttsPitch })}</span>
                        <input
                          type="range" min={-10} max={10} step={1} value={voice.ttsPitch}
                          onChange={(e) => updateVoice({ ttsPitch: Number(e.target.value) })}
                          className="w-full"
                          aria-label={t("upload.ttsPitch", { pitch: voice.ttsPitch })}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </Card>

            <Card className="mt-6 flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-bold">{t("upload.estimateTitle")}</h3>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {formatBytes(file.size)}
                  {duration > 0 && ` · ${formatDuration(duration)}`} · ⏱{" "}
                  {estMinutes <= 1
                    ? t("upload.estimatedTimeShort")
                    : t("upload.estimatedTime", { minutes: estMinutes })}
                </p>
              </div>
              <Button size="lg" onClick={startUpload} className="shrink-0">
                ✨ {t("upload.startUpload")}
              </Button>
            </Card>
          </motion.div>
        )}

        {uploading && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="p-8 text-center">
              <div
                aria-hidden
                className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-violet-500/20"
              >
                <span className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500/30 border-t-indigo-500" />
              </div>
              <ProgressBar
                value={progress}
                label={t("upload.progressLabel")}
              />
              <p className="mt-3 text-sm text-[var(--muted)]">
                {t("upload.uploading", { pct: progress })}
              </p>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default function UploadPage() {
  return (
    <RequireAuth>
      <AppShell>
        <UploadContent />
      </AppShell>
    </RequireAuth>
  );
}
