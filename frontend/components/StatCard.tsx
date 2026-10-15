"use client";

import { motion } from "framer-motion";
import Card from "@/components/Card";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: string;
  accent?: string;
  sub?: string;
}

export default function StatCard({ label, value, icon, accent, sub }: StatCardProps) {
  return (
    <Card hover className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full bg-gradient-to-br from-blue-500/15 to-violet-500/15 blur-2xl"
      />
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-[var(--muted)]">{label}</p>
          <motion.p
            key={String(value)}
            initial={{ opacity: 0.4, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1 text-3xl font-extrabold tabular-nums tracking-tight"
          >
            {value}
          </motion.p>
          {sub && <p className="mt-1 text-xs text-[var(--muted)]">{sub}</p>}
        </div>
        <div
          aria-hidden
          className={`flex h-11 w-11 items-center justify-center rounded-xl text-xl ${
            accent ?? "bg-gradient-to-br from-blue-500/20 to-violet-500/20"
          }`}
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}
