"use client";

import { useT } from "@/lib/i18n";
import LegalLayout, { LegalSection } from "@/components/LegalLayout";
import { legalContent } from "@/lib/legalContent";

export default function ContentPolicyPage() {
  const { t, locale } = useT();
  const sections = legalContent[locale].contentPolicy;
  return (
    <LegalLayout title={t("legal.contentPolicyTitle")} updated={t("legal.lastUpdated")}>
      {sections.map((s) => (
        <LegalSection key={s.h} h={s.h} p={s.p} />
      ))}
    </LegalLayout>
  );
}
