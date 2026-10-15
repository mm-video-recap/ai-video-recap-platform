"use client";

import { motion } from "framer-motion";
import Button from "@/components/Button";
import { useT } from "@/lib/i18n";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export default function ErrorState({ title, message, onRetry }: ErrorStateProps) {
  const { t } = useT();
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      role="alert"
      className="flex flex-col items-center justify-center rounded-2xl border border-red-500/25 bg-red-500/5 px-6 py-14 text-center"
    >
      <div
        aria-hidden
        className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/15 text-3xl"
      >
        ⚠️
      </div>
      <h3 className="text-lg font-bold">{title ?? t("errors.generic")}</h3>
      {message && (
        <p className="mt-1 max-w-sm text-sm text-[var(--muted)]">{message}</p>
      )}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry} className="mt-5">
          {t("common.retry")}
        </Button>
      )}
    </motion.div>
  );
}
