"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { postBugReport, postFeatureReport } from "@/lib/api";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import Card from "@/components/Card";
import Button from "@/components/Button";

function useReportForm() {
  const { getAccessToken } = useAuth();
  const { toast } = useToast();
  const { t } = useT();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const send = async (fn: (token: string | null) => Promise<unknown>) => {
    setSending(true);
    try {
      const token = await getAccessToken();
      await fn(token);
      setSent(true);
      toast(t("contact.sent"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setSending(false);
    }
  };

  return { sending, sent, send, reset: () => setSent(false) };
}

function SupportForm() {
  const { t } = useT();
  const { sending, sent, send } = useReportForm();
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [jobId, setJobId] = useState("");

  return (
    <Card className="p-6">
      {sent ? (
        <p role="status" className="py-6 text-center font-bold text-emerald-600 dark:text-emerald-300">
          ✅ {t("contact.sent")}
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send((token) =>
              postBugReport(token, {
                subject: `[Support] ${subject}`,
                body: message,
                job_id: jobId.trim() || undefined,
              })
            );
          }}
          className="space-y-4"
        >
          <h2 className="text-lg font-bold">💬 {t("contact.supportTitle")}</h2>
          <div>
            <label htmlFor="sup-subject" className="label-text">{t("contact.subject")}</label>
            <input id="sup-subject" required value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("contact.subjectPlaceholder")} className="input-field" />
          </div>
          <div>
            <label htmlFor="sup-job" className="label-text">
              {t("contact.jobId")} ({t("common.optional")})
            </label>
            <input id="sup-job" value={jobId} onChange={(e) => setJobId(e.target.value)} className="input-field font-mono" />
          </div>
          <div>
            <label htmlFor="sup-msg" className="label-text">{t("contact.message")}</label>
            <textarea id="sup-msg" required rows={4} value={message} onChange={(e) => setMessage(e.target.value)} placeholder={t("contact.messagePlaceholder")} className="input-field resize-none" />
          </div>
          <Button type="submit" loading={sending}>{t("contact.send")}</Button>
        </form>
      )}
    </Card>
  );
}

function BugForm() {
  const { t } = useT();
  const { sending, sent, send } = useReportForm();
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [jobId, setJobId] = useState("");

  return (
    <Card className="p-6">
      {sent ? (
        <p role="status" className="py-6 text-center font-bold text-emerald-600 dark:text-emerald-300">
          ✅ {t("contact.sent")}
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send((token) =>
              postBugReport(token, {
                subject: `[Bug] ${subject}`,
                body: message,
                job_id: jobId.trim() || undefined,
              })
            );
          }}
          className="space-y-4"
        >
          <h2 className="text-lg font-bold">🐞 {t("contact.bugTitle")}</h2>
          <div>
            <label htmlFor="bug-subject" className="label-text">{t("contact.subject")}</label>
            <input id="bug-subject" required value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("contact.subjectPlaceholder")} className="input-field" />
          </div>
          <div>
            <label htmlFor="bug-job" className="label-text">
              {t("contact.jobId")} ({t("common.optional")})
            </label>
            <input id="bug-job" value={jobId} onChange={(e) => setJobId(e.target.value)} className="input-field font-mono" />
          </div>
          <div>
            <label htmlFor="bug-msg" className="label-text">{t("contact.message")}</label>
            <textarea id="bug-msg" required rows={4} value={message} onChange={(e) => setMessage(e.target.value)} placeholder={t("contact.messagePlaceholder")} className="input-field resize-none" />
          </div>
          <Button type="submit" loading={sending}>{t("contact.send")}</Button>
        </form>
      )}
    </Card>
  );
}

function FeatureForm() {
  const { t } = useT();
  const { sending, sent, send } = useReportForm();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  return (
    <Card className="p-6">
      {sent ? (
        <p role="status" className="py-6 text-center font-bold text-emerald-600 dark:text-emerald-300">
          ✅ {t("contact.sent")}
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send((token) => postFeatureReport(token, { title, body }));
          }}
          className="space-y-4"
        >
          <h2 className="text-lg font-bold">💡 {t("contact.featureTitle")}</h2>
          <div>
            <label htmlFor="feat-title" className="label-text">{t("contact.titleField")}</label>
            <input id="feat-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("contact.titlePlaceholder")} className="input-field" />
          </div>
          <div>
            <label htmlFor="feat-body" className="label-text">{t("contact.message")}</label>
            <textarea id="feat-body" required rows={4} value={body} onChange={(e) => setBody(e.target.value)} placeholder={t("contact.messagePlaceholder")} className="input-field resize-none" />
          </div>
          <Button type="submit" loading={sending}>{t("contact.send")}</Button>
        </form>
      )}
    </Card>
  );
}

export default function ContactPage() {
  const { t } = useT();

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-12 sm:px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-8 text-center">
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{t("contact.title")}</h1>
          <p className="mx-auto mt-2 max-w-xl text-[var(--muted)]">{t("contact.subtitle")}</p>
        </motion.div>

        <div className="grid gap-6 md:grid-cols-2">
          <SupportForm />
          <BugForm />
          <FeatureForm />
          <Card className="p-6">
            <h2 className="text-lg font-bold">🔒 {t("contact.securityTitle")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
              {t("contact.securityDesc")}
            </p>
            <a
              href={`mailto:${t("contact.securityEmail")}`}
              className="mt-4 inline-block rounded-xl border border-[var(--border)] px-4 py-2.5 font-mono text-sm font-semibold transition-colors hover:border-indigo-500/60"
            >
              {t("contact.securityEmail")}
            </a>
          </Card>
        </div>
      </main>
      <Footer />
    </div>
  );
}
