"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useT, useTArray } from "@/lib/i18n";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import Button from "@/components/Button";
import Card from "@/components/Card";
import PipelineAnimation from "@/components/PipelineAnimation";

const fadeUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.55, ease: "easeOut" as const },
};

function SectionHeading({ kicker, title, sub }: { kicker: string; title: string; sub: string }) {
  return (
    <motion.div {...fadeUp} className="mx-auto mb-12 max-w-2xl text-center">
      <p className="mb-3 text-sm font-bold uppercase tracking-[0.2em] text-indigo-500 dark:text-indigo-300">
        {kicker}
      </p>
      <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{title}</h2>
      <p className="mt-3 text-[var(--muted)]">{sub}</p>
    </motion.div>
  );
}

function Hero() {
  const { t } = useT();
  const stats = useTArray<{ label: string; value: string }>("hero.stats");

  return (
    <section className="relative overflow-hidden">
      {/* Background blobs */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-32 left-1/4 h-96 w-96 rounded-full bg-blue-600/20 blur-[120px]" />
        <div className="absolute -top-16 right-1/4 h-96 w-96 rounded-full bg-violet-600/20 blur-[120px]" />
      </div>

      <div className="relative mx-auto max-w-7xl px-4 pb-16 pt-16 text-center sm:px-6 sm:pt-24">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-semibold text-indigo-600 dark:text-indigo-300"
        >
          <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          {t("hero.badge")}
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.6 }}
          className="mx-auto max-w-4xl text-balance text-4xl font-extrabold leading-tight tracking-tight sm:text-6xl"
        >
          {t("hero.titleA")}{" "}
          <span className="text-gradient">{t("hero.titleB")}</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="mx-auto mt-6 max-w-2xl text-lg text-[var(--muted)]"
        >
          {t("hero.subtitle")}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.6 }}
          className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <Link href="/upload">
            <Button size="lg" className="w-full sm:w-auto">
              {t("hero.primaryCta")} →
            </Button>
          </Link>
          <Link href="#demo">
            <Button size="lg" variant="secondary" className="w-full sm:w-auto">
              ▶ {t("hero.secondaryCta")}
            </Button>
          </Link>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.8 }}
          className="mt-14"
        >
          <PipelineAnimation />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.6 }}
          className="mx-auto mt-10 grid max-w-2xl grid-cols-3 gap-4"
        >
          {stats.map((s) => (
            <div key={s.label} className="card px-4 py-5">
              <p className="text-2xl font-extrabold text-gradient sm:text-3xl">{s.value}</p>
              <p className="mt-1 text-xs text-[var(--muted)] sm:text-sm">{s.label}</p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

const FEATURE_ICONS = ["📝", "💬", "⭐", "🗂️", "📄", "🎁"];

function Features() {
  const { t } = useT();
  const items = useTArray<{ title: string; desc: string }>("features.items");
  return (
    <section id="features" className="mx-auto max-w-7xl scroll-mt-20 px-4 py-20 sm:px-6">
      <SectionHeading
        kicker={t("nav.features")}
        title={t("features.heading")}
        sub={t("features.subheading")}
      />
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((f, i) => (
          <motion.div key={f.title} {...fadeUp} transition={{ ...fadeUp.transition, delay: (i % 3) * 0.08 }}>
            <Card hover className="h-full">
              <div
                aria-hidden
                className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/20 to-violet-500/20 text-2xl"
              >
                {FEATURE_ICONS[i] ?? "✨"}
              </div>
              <h3 className="text-lg font-bold">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{f.desc}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function HowItWorks() {
  const { t } = useT();
  const steps = useTArray<{ title: string; desc: string }>("howItWorks.steps");
  return (
    <section id="how-it-works" className="scroll-mt-20 border-y divider bg-[var(--surface)]/50 py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <SectionHeading
          kicker={t("nav.howItWorks")}
          title={t("howItWorks.heading")}
          sub={t("howItWorks.subheading")}
        />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <motion.div key={s.title} {...fadeUp} transition={{ ...fadeUp.transition, delay: i * 0.08 }}>
              <Card className="relative h-full overflow-hidden">
                <span
                  aria-hidden
                  className="absolute -right-2 -top-4 text-7xl font-extrabold text-indigo-500/10"
                >
                  {i + 1}
                </span>
                <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 text-base font-extrabold text-white">
                  {i + 1}
                </div>
                <h3 className="font-bold">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{s.desc}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

const TECH_ICONS = ["🎙️", "🧠", "🎬", "⚙️"];

function Technology() {
  const { t } = useT();
  const items = useTArray<{ title: string; desc: string }>("technology.items");
  return (
    <section id="technology" className="mx-auto max-w-7xl scroll-mt-20 px-4 py-20 sm:px-6">
      <SectionHeading
        kicker={t("nav.technology")}
        title={t("technology.heading")}
        sub={t("technology.subheading")}
      />
      <div className="grid gap-5 md:grid-cols-2">
        {items.map((item, i) => (
          <motion.div key={item.title} {...fadeUp} transition={{ ...fadeUp.transition, delay: (i % 2) * 0.08 }}>
            <Card hover className="flex h-full gap-4">
              <div
                aria-hidden
                className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-violet-500/20 text-3xl"
              >
                {TECH_ICONS[i] ?? "⚙️"}
              </div>
              <div>
                <h3 className="text-lg font-bold">{item.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted)]">{item.desc}</p>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function Demo() {
  const { t } = useT();
  return (
    <section id="demo" className="scroll-mt-20 border-y divider bg-[var(--surface)]/50 py-20">
      <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
        <SectionHeading
          kicker={t("hero.secondaryCta")}
          title={t("demo.heading")}
          sub={t("demo.subheading")}
        />
        <motion.div {...fadeUp} className="relative mx-auto max-w-3xl">
          <div className="glass relative overflow-hidden rounded-2xl p-10 shadow-card sm:p-16">
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-br from-blue-600/10 via-transparent to-violet-600/10" />
            <div aria-hidden className="mx-auto mb-6 flex h-24 w-24 animate-float items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-600 text-4xl text-white shadow-glow-lg">
              ▶
            </div>
            <p className="text-[var(--muted)]">{t("demo.note")}</p>
            <Link href="/upload" className="mt-6 inline-block">
              <Button>{t("hero.primaryCta")}</Button>
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Faq() {
  const { t } = useT();
  const items = useTArray<{ q: string; a: string }>("faq.items");
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-4 py-20 sm:px-6">
      <SectionHeading
        kicker={t("nav.faq")}
        title={t("faq.heading")}
        sub={t("faq.subheading")}
      />
      <div className="space-y-3">
        {items.map((item, i) => {
          const isOpen = open === i;
          return (
            <motion.div key={item.q} {...fadeUp} className="card overflow-hidden">
              <button
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
              >
                <span className="font-bold">{item.q}</span>
                <motion.span
                  aria-hidden
                  animate={{ rotate: isOpen ? 45 : 0 }}
                  className="text-xl text-indigo-500"
                >
                  +
                </motion.span>
              </button>
              <motion.div
                initial={false}
                animate={{ height: isOpen ? "auto" : 0, opacity: isOpen ? 1 : 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden"
              >
                <p className="px-5 pb-5 text-sm leading-relaxed text-[var(--muted)]">{item.a}</p>
              </motion.div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

function Community() {
  const { t } = useT();
  return (
    <section id="community" className="mx-auto max-w-7xl scroll-mt-20 px-4 pb-20 sm:px-6">
      <motion.div
        {...fadeUp}
        className="relative overflow-hidden rounded-3xl border border-indigo-500/25 bg-gradient-to-br from-blue-600/15 via-indigo-600/10 to-violet-600/15 p-10 text-center sm:p-16"
      >
        <div aria-hidden className="pointer-events-none absolute -left-20 -top-20 h-64 w-64 rounded-full bg-blue-500/20 blur-[100px]" />
        <div aria-hidden className="pointer-events-none absolute -bottom-20 -right-20 h-64 w-64 rounded-full bg-violet-500/20 blur-[100px]" />
        <h2 className="relative text-3xl font-extrabold sm:text-4xl">{t("community.heading")}</h2>
        <p className="relative mx-auto mt-4 max-w-xl text-[var(--muted)]">{t("community.desc")}</p>
        <Link href="/contact" className="relative mt-8 inline-block">
          <Button size="lg">{t("community.cta")}</Button>
        </Link>
      </motion.div>
    </section>
  );
}

function FinalCta() {
  const { t } = useT();
  return (
    <section className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
      <motion.div {...fadeUp} className="text-center">
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          {t("ctaSection.heading")}
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-[var(--muted)]">{t("ctaSection.desc")}</p>
        <Link href="/upload" className="mt-8 inline-block">
          <Button size="lg">{t("ctaSection.button")} →</Button>
        </Link>
      </motion.div>
    </section>
  );
}

export default function Home() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Technology />
        <Demo />
        <Faq />
        <Community />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
