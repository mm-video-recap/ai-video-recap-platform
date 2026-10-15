"use client";

import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { STAGE_ORDER, type StageKey } from "@/lib/utils";
import ProgressBar from "@/components/ProgressBar";

const STEP_ICONS: Record<StageKey, string> = {
  upload: "📤",
  audio: "🎵",
  speech: "🎙️",
  analysis: "🧠",
  summary: "📝",
  highlights: "⭐",
  rendering: "🎬",
  completed: "✅",
};

interface ProcessingStepsProps {
  currentStage: StageKey;
  progress: number;
  message?: string;
}

/** Animated vertical AI pipeline visualization fed by live job state. */
export default function ProcessingSteps({
  currentStage,
  progress,
  message,
}: ProcessingStepsProps) {
  const { t } = useT();
  const currentIdx = STAGE_ORDER.indexOf(currentStage);

  return (
    <div className="card p-6">
      <div className="mb-5">
        <ProgressBar value={progress} label={t("processing.overallProgress")} />
      </div>
      <ol className="relative space-y-1">
        {STAGE_ORDER.map((stage, i) => {
          const done = i < currentIdx || currentStage === "completed";
          const active = i === currentIdx && currentStage !== "completed";
          return (
            <li key={stage} className="relative">
              {i < STAGE_ORDER.length - 1 && (
                <span
                  aria-hidden
                  className={`absolute left-[27px] top-14 h-[calc(100%-3rem)] w-0.5 ${
                    done ? "bg-gradient-to-b from-indigo-500 to-violet-500" : "bg-[var(--border)]"
                  }`}
                />
              )}
              <motion.div
                initial={false}
                animate={active ? { scale: [1, 1.015, 1] } : { scale: 1 }}
                transition={active ? { duration: 1.6, repeat: Infinity } : {}}
                className={`flex items-start gap-4 rounded-xl p-3 transition-colors ${
                  active ? "bg-indigo-500/10" : ""
                }`}
              >
                <div className="relative flex-shrink-0">
                  {active && (
                    <span
                      aria-hidden
                      className="absolute inset-0 rounded-2xl bg-indigo-500/40 animate-pulse-ring"
                    />
                  )}
                  <div
                    aria-hidden
                    className={`relative flex h-14 w-14 items-center justify-center rounded-2xl text-2xl ${
                      done
                        ? "bg-gradient-to-br from-emerald-500/25 to-emerald-600/10"
                        : active
                          ? "bg-gradient-to-br from-blue-500/30 to-violet-500/30 shadow-glow"
                          : "bg-[var(--surface-2)] opacity-60"
                    }`}
                  >
                    {done ? (
                      <span className="text-emerald-500">✓</span>
                    ) : active ? (
                      <span className="animate-spin-slow">{STEP_ICONS[stage]}</span>
                    ) : (
                      <span className="grayscale">{STEP_ICONS[stage]}</span>
                    )}
                  </div>
                </div>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <h3
                      className={`font-bold ${active ? "text-gradient" : ""} ${
                        !done && !active ? "text-[var(--muted)]" : ""
                      }`}
                    >
                      {t(`processing.steps.${stage}`)}
                    </h3>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        done
                          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                          : active
                            ? "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300"
                            : "bg-[var(--surface-2)] text-[var(--muted)]"
                      }`}
                    >
                      {done
                        ? t("processing.statusDone")
                        : active
                          ? t("processing.statusActive")
                          : t("processing.statusPending")}
                    </span>
                  </div>
                  <p className="mt-0.5 text-sm text-[var(--muted)]">
                    {active && message
                      ? message
                      : t(`processing.stepDescs.${stage}`)}
                  </p>
                  {active && (
                    <div className="mt-2 max-w-xs">
                      <ProgressBar value={progress} showPercent={false} size="sm" />
                    </div>
                  )}
                </div>
              </motion.div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
