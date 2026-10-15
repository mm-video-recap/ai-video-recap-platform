"use client";

import { motion } from "framer-motion";

interface ProgressBarProps {
  value: number; // 0..100
  label?: string;
  showPercent?: boolean;
  size?: "sm" | "md";
}

export default function ProgressBar({
  value,
  label,
  showPercent = true,
  size = "md",
}: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="w-full">
      {(label || showPercent) && (
        <div className="mb-1.5 flex items-center justify-between text-sm">
          {label && <span className="font-medium">{label}</span>}
          {showPercent && (
            <span className="tabular-nums text-[var(--muted)]">{pct}%</span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className={`w-full overflow-hidden rounded-full bg-[var(--surface-2)] ${
          size === "sm" ? "h-1.5" : "h-2.5"
        }`}
      >
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 via-indigo-500 to-violet-500"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", damping: 25, stiffness: 120 }}
        />
      </div>
    </div>
  );
}
