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
  const { getAccessToken } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const prefs = useMemo(() => loadPreferences(), []);
  const [summaryLang, setSummaryLang] = useState<"my" | "en">(prefs.defaultLanguage as "my" | "en");
  const [subtitleLang, setSubtitleLang] = useState<Lang>(prefs.defaultLanguage as "my" | "en");
  const [recapStyle, setRecapStyle] = useState(prefs.summaryStyle);
  const [introEnabled, setIntroEnabled] = useState(true);
  const [outroEnabled, setOutroEnabled] = useState(true);

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
          // output_lang / subtitle_language / recap_style are sent as query
          // params (see lib/api.ts) and persisted on the backend Job.
          output_lang: summaryLang,
          subtitle_language: subtitleLang,
          recap_style: recapStyle,
          intro_enabled: String(introEnabled),
          outro_enabled: String(outroEnabled),
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
                  <span className="label-text">{t("upload.recapStyle")}</span>
                  {segmented(recapStyle, setRecapStyle, [
                    { value: "concise", label: t("upload.styles.concise") },
                    { value: "detailed", label: t("upload.styles.detailed") },
                    { value: "highlights", label: t("upload.styles.highlights") },
                  ])}
                  <p className="mt-2 text-xs text-[var(--muted)]">
                    {t(`upload.stylesDesc.${recapStyle}`)}
                  </p>
                </div>
                <div>
                  <span className="label-text">{t("upload.introOutro")}</span>
                  <div className="space-y-3">
                    {toggleRow(t("upload.introEnabled"), introEnabled, setIntroEnabled)}
                    {toggleRow(t("upload.outroEnabled"), outroEnabled, setOutroEnabled)}
                  </div>
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
