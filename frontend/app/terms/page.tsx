"use client";

import { useT } from "@/lib/i18n";
import LegalLayout, { LegalSection } from "@/components/LegalLayout";
import { legalContent } from "@/lib/legalContent";

export default function TermsPage() {
  const { t, locale } = useT();
  const sections = legalContent[locale].terms;
  return (
    <LegalLayout title={t("legal.termsTitle")} updated={t("legal.lastUpdated")}>
      {sections.map((s) => (
        <LegalSection key={s.h} h={s.h} p={s.p} />
      ))}
    </LegalLayout>
  );
}
