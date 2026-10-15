"use client";

import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";

/** Animated video → AI → recap pipeline visual for the landing hero. */
export default function PipelineAnimation() {
  const { t } = useT();

  const nodes = [
    { key: "upload", icon: "🎬", delay: 0 },
    { key: "ai", icon: "🧠", delay: 0.25 },
    { key: "recap", icon: "✨", delay: 0.5 },
  ];

  return (
    <div
      aria-hidden
      className="relative mx-auto flex max-w-2xl items-center justify-between px-2 py-6"
    >
      {/* Animated connector line */}
      <svg
        className="absolute inset-x-8 top-1/2 h-1 -translate-y-1/2"
        preserveAspectRatio="none"
        viewBox="0 0 100 2"
      >
        <line
          x1="0"
          y1="1"
          x2="100"
          y2="1"
          stroke="url(#pipeGrad)"
          strokeWidth="2"
          strokeDasharray="6 6"
          className="animate-dash"
        />
        <defs>
          <linearGradient id="pipeGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="50%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
      </svg>

      {nodes.map((n) => (
        <div key={n.key} className="relative z-10 flex flex-col items-center gap-3">
          <motion.div
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 4, repeat: Infinity, delay: n.delay, ease: "easeInOut" }}
            className={`flex h-20 w-20 items-center justify-center rounded-3xl text-4xl shadow-card sm:h-24 sm:w-24 ${
              n.key === "ai"
                ? "bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-white shadow-glow-lg"
                : "glass"
            }`}
          >
            {n.icon}
          </motion.div>
          <span className="rounded-full bg-[var(--surface)] px-3 py-1 text-xs font-bold shadow">
            {t(`pipelineAnim.${n.key}`)}
          </span>
        </div>
      ))}

      {/* Travelling pulse dots */}
      {[0, 1].map((i) => (
        <motion.span
          key={i}
          className="absolute top-1/2 z-10 h-3 w-3 -translate-y-1/2 rounded-full bg-indigo-400 shadow-glow"
          animate={{ left: ["8%", "90%"], opacity: [0, 1, 1, 0] }}
          transition={{ duration: 3, repeat: Infinity, delay: i * 1.5, ease: "linear" }}
        />
      ))}
    </div>
  );
}
