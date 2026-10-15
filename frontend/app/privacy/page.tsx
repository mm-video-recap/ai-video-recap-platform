"use client";

import { useT } from "@/lib/i18n";
import LegalLayout, { LegalSection } from "@/components/LegalLayout";
import { legalContent } from "@/lib/legalContent";

export default function PrivacyPage() {
  const { t, locale } = useT();
  const sections = legalContent[locale].privacy;
  return (
    <LegalLayout title={t("legal.privacyTitle")} updated={t("legal.lastUpdated")}>
      <p className="rounded-2xl border border-indigo-500/25 bg-indigo-500/5 p-5 leading-relaxed">
        {t("legal.privacyIntro")}
      </p>
      {sections.map((s) => (
        <LegalSection key={s.h} h={s.h} p={s.p} />
      ))}
    </LegalLayout>
  );
}
