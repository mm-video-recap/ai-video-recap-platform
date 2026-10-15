"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { formatBytes, ACCEPTED_VIDEO_TYPES, getExtension } from "@/lib/utils";

interface FileUploaderProps {
  file: File | null;
  onFile: (f: File | null) => void;
  error: string | null;
}

/** Premium drag-drop uploader with live video preview. */
export default function FileUploader({ file, onFile, error }: FileUploaderProps) {
  const { t } = useT();
  const [dragOver, setDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pick = useCallback(
    (f: File | undefined | null) => {
      if (f) onFile(f);
    },
    [onFile]
  );

  return (
    <div>
      {!file ? (
        <motion.div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pick(e.dataTransfer.files?.[0]);
          }}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          role="button"
          tabIndex={0}
          aria-label={t("upload.dropTitle")}
          animate={dragOver ? { scale: 1.01 } : { scale: 1 }}
          className={`relative cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-10 text-center transition-all sm:p-14 ${
            dragOver
              ? "border-indigo-500 bg-indigo-500/10 shadow-glow"
              : "border-[var(--border)] bg-[var(--surface)] hover:border-indigo-500/60 hover:bg-indigo-500/5"
          }`}
        >
          <motion.div
            animate={dragOver ? { y: -6, scale: 1.1 } : { y: [0, -6, 0] }}
            transition={
              dragOver ? { duration: 0.2 } : { duration: 3, repeat: Infinity }
            }
            aria-hidden
            className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-violet-500/20 text-3xl"
          >
            🎬
          </motion.div>
          <p className="text-lg font-bold">{t("upload.dropTitle")}</p>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {t("upload.dropSubtitle")} ·{" "}
            <span className="font-semibold text-indigo-500 dark:text-indigo-300">
              {t("upload.browse")}
            </span>
          </p>
          <p className="mt-3 text-xs text-[var(--muted)]">{t("upload.supported")}</p>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_VIDEO_TYPES.map((e) => `.${e}`).join(",")}
            className="sr-only"
            aria-hidden
            tabIndex={-1}
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="card overflow-hidden p-4"
        >
          <div className="flex flex-col gap-4 sm:flex-row">
            {previewUrl && (
              <video
                src={previewUrl}
                muted
                playsInline
                preload="metadata"
                className="h-36 w-full rounded-xl bg-black object-cover sm:w-56"
              />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold">{file.name}</p>
                  <p className="mt-1 text-xs uppercase tracking-wide text-[var(--muted)]">
                    {getExtension(file.name) || "video"} · {formatBytes(file.size)}
                  </p>
                </div>
                <button
                  onClick={() => onFile(null)}
                  aria-label={t("upload.remove")}
                  className="rounded-lg px-2 py-1 text-sm text-[var(--muted)] transition-colors hover:bg-red-500/10 hover:text-red-500"
                >
                  ✕ {t("upload.remove")}
                </button>
              </div>
              <div className="mt-3 flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-300">
                <span aria-hidden>✓</span>
                {t("upload.supported")}
              </div>
            </div>
          </div>
        </motion.div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm font-medium text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
