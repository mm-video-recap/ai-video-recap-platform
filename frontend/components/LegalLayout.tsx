"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

/** Shared shell for legal / info pages: top nav, centered article, footer. */
export default function LegalLayout({
  title,
  updated,
  children,
}: {
  title: string;
  updated?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{title}</h1>
          {updated && (
            <p className="mt-2 text-sm text-[var(--muted)]">{updated}</p>
          )}
        </motion.div>
        <motion.article
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="prose-custom mt-8 space-y-8"
        >
          {children}
        </motion.article>
      </main>
      <Footer />
    </div>
  );
}

export function LegalSection({ h, p }: { h: string; p: string[] }) {
  return (
    <section>
      <h2 className="mb-3 text-xl font-bold">{h}</h2>
      <div className="space-y-2.5">
        {p.map((para, i) => (
          <p key={i} className="leading-relaxed text-[var(--muted)]">
            {para}
          </p>
        ))}
      </div>
    </section>
  );
}
