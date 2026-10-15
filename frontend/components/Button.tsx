"use client";

import { motion } from "framer-motion";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
  loading?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary: "btn-gradient",
  secondary:
    "bg-[var(--surface-2)] border border-[var(--border)] hover:border-indigo-500/50 hover:bg-indigo-500/10 text-[var(--foreground)]",
  ghost: "hover:bg-[var(--surface-2)] text-[var(--foreground)]",
  danger:
    "bg-red-500/15 border border-red-500/40 text-red-600 dark:text-red-300 hover:bg-red-500/25",
  outline:
    "border border-[var(--border)] hover:border-indigo-500/60 text-[var(--foreground)]",
};

const SIZES: Record<Size, string> = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-6 text-sm",
  lg: "px-8 text-base py-3.5",
};

export default function Button({
  variant = "primary",
  size = "md",
  children,
  loading,
  disabled,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all focus-visible:outline-2 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...(rest as object)}
    >
      {loading && (
        <span
          aria-hidden
          className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
        />
      )}
      {children}
    </motion.button>
  );
}
