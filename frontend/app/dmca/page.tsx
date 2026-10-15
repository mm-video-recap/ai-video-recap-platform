"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { postBugReport } from "@/lib/api";
import LegalLayout, { LegalSection } from "@/components/LegalLayout";
import { legalContent } from "@/lib/legalContent";
import Button from "@/components/Button";
import Card from "@/components/Card";

export default function DmcaPage() {
  const { t, locale } = useT();
  const { getAccessToken } = useAuth();
  const { toast } = useToast();
  const sections = legalContent[locale].dmcaInfo;

  const [workTitle, setWorkTitle] = useState("");
  const [workUrl, setWorkUrl] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreed) return;
    setSending(true);
    try {
      const token = await getAccessToken();
      await postBugReport(token, {
        subject: `[DMCA] ${workTitle}`,
        body: `Copyrighted work: ${workTitle}\nInfringing URL: ${workUrl}\nReporter: ${name} <${email}>\n\n${t("dmca.statementText")}`,
      });
      setSent(true);
      toast(t("dmca.submitted"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <LegalLayout title={t("legal.dmcaTitle")} updated={t("legal.lastUpdated")}>
      <p className="rounded-2xl border border-indigo-500/25 bg-indigo-500/5 p-5 leading-relaxed">
        {t("dmca.desc")}
      </p>
      {sections.map((s) => (
        <LegalSection key={s.h} h={s.h} p={s.p} />
      ))}

      <Card className="mt-4 p-6">
        {sent ? (
          <p role="status" className="py-6 text-center font-bold text-emerald-600 dark:text-emerald-300">
            ✅ {t("dmca.submitted")}
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <h2 className="text-xl font-bold">{t("dmca.formTitle")}</h2>
            <div>
              <label htmlFor="dmca-work" className="label-text">{t("dmca.workTitle")}</label>
              <input id="dmca-work" required value={workTitle} onChange={(e) => setWorkTitle(e.target.value)} className="input-field" />
            </div>
            <div>
              <label htmlFor="dmca-url" className="label-text">{t("dmca.workUrl")}</label>
              <input id="dmca-url" required type="url" value={workUrl} onChange={(e) => setWorkUrl(e.target.value)} className="input-field" placeholder="https://" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="dmca-name" className="label-text">{t("dmca.yourName")}</label>
                <input id="dmca-name" required value={name} onChange={(e) => setName(e.target.value)} className="input-field" />
              </div>
              <div>
                <label htmlFor="dmca-email" className="label-text">{t("dmca.yourEmail")}</label>
                <input id="dmca-email" required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" />
              </div>
            </div>
            <label className="flex cursor-pointer items-start gap-3 rounded-xl bg-[var(--surface-2)]/60 p-4 text-sm">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-1 h-4 w-4 accent-indigo-600"
              />
              <span>
                <span className="font-bold">{t("dmca.statement")}: </span>
                {t("dmca.statementText")}
              </span>
            </label>
            <Button type="submit" loading={sending} disabled={!agreed}>
              {t("dmca.submit")}
            </Button>
          </form>
        )}
      </Card>
    </LegalLayout>
  );
}
