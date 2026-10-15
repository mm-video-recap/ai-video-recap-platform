"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";

interface DropdownProps {
  label: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
  ariaLabel?: string;
}

export default function Dropdown({ label, children, align = "right", ariaLabel }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel}
        className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors hover:bg-[var(--surface-2)]"
      >
        {label}
        <span aria-hidden className={`text-xs transition-transform ${open ? "rotate-180" : ""}`}>
          ▾
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            role="menu"
            className={`card absolute z-50 mt-2 min-w-[11rem] overflow-hidden p-1.5 shadow-card ${
              align === "right" ? "right-0" : "left-0"
            }`}
          >
            <div onClick={() => setOpen(false)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function DropdownItem({
  children,
  onClick,
  danger,
}: {
  children: ReactNode;
  onClick?: () => void;
  danger?: boolean;
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--surface-2)] ${
        danger ? "text-red-500" : ""
      }`}
    >
      {children}
    </button>
  );
}
