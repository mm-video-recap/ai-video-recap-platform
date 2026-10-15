"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import en from "@/locales/en.json";
import my from "@/locales/my.json";
import type { Locale } from "@/lib/types";

const DICTS: Record<Locale, Record<string, unknown>> = {
  en: en as unknown as Record<string, unknown>,
  my: my as unknown as Record<string, unknown>,
};

const STORAGE_KEY = "locale";

function resolveDefaultLocale(): Locale {
  const env = process.env.NEXT_PUBLIC_DEFAULT_LOCALE;
  return env === "en" ? "en" : "my";
}

function lookup(dict: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, dict);
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  /** Translate a dotted key, e.g. t("hero.titleA"). Supports {var} interpolation. */
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => resolveDefaultLocale());

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "en" || stored === "my") {
        setLocaleState(stored);
      }
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "my" ? "my" : "en";
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const dict = DICTS[locale] ?? DICTS.my;
      let value = lookup(dict, key);
      if (value === undefined) {
        // Fallback to English, then to the key itself.
        value = lookup(DICTS.en, key);
      }
      if (typeof value !== "string") return key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          value = (value as string).replaceAll(`{${k}}`, String(v));
        }
      }
      return value as string;
    },
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Tiny translation hook used across the app. */
export function useT(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useT must be used inside <I18nProvider>");
  return ctx;
}

/** Get a translated array from the dictionary (e.g. faq items). */
export function useTArray<T = { title: string; desc: string }>(key: string): T[] {
  const { locale } = useT();
  const dict = DICTS[locale] ?? DICTS.my;
  const value = lookup(dict, key);
  if (Array.isArray(value)) return value as T[];
  const fallback = lookup(DICTS.en, key);
  return Array.isArray(fallback) ? (fallback as T[]) : [];
}
