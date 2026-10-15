"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useT } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import Button from "@/components/Button";
import Card from "@/components/Card";

export default function LoginPage() {
  const { t } = useT();
  const { user, loading, signIn, signUp, signInWithGoogle } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "login") {
        const { error: err } = await signIn(email, password);
        if (err) {
          setError(t("auth.errorInvalid"));
        } else {
          router.push("/dashboard");
        }
      } else {
        const { error: err } = await signUp(email, password, name);
        if (err) {
          setError(t("auth.errorGeneric"));
        } else {
          toast(t("auth.checkEmail"), "success");
          setMode("login");
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    const { error: err } = await signInWithGoogle();
    if (err) {
      setError(t("auth.errorGeneric"));
      toast(t("auth.errorGeneric"), "error");
    }
    // On success Supabase redirects to /dashboard via OAuth flow.
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-12">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/4 top-10 h-72 w-72 rounded-full bg-blue-600/15 blur-[100px]" />
          <div className="absolute bottom-10 right-1/4 h-72 w-72 rounded-full bg-violet-600/15 blur-[100px]" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative w-full max-w-md"
        >
          <Card className="p-8 shadow-card">
            <div className="mb-6 text-center">
              <span
                aria-hidden
                className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 text-2xl text-white shadow-glow"
              >
                ▶
              </span>
              <h1 className="text-2xl font-extrabold">
                {mode === "login" ? t("auth.loginTitle") : t("auth.signUpTitle")}
              </h1>
              <p className="mt-1.5 text-sm text-[var(--muted)]">
                {mode === "login" ? t("auth.loginSubtitle") : t("auth.signUpSubtitle")}
              </p>
            </div>

            <Button
              variant="secondary"
              className="w-full"
              onClick={handleGoogle}
              type="button"
            >
              <span aria-hidden className="text-lg font-bold">G</span>
              {t("auth.google")}
            </Button>

            <div className="my-5 flex items-center gap-3 text-xs text-[var(--muted)]">
              <span className="h-px flex-1 bg-[var(--border)]" />
              {t("auth.or")}
              <span className="h-px flex-1 bg-[var(--border)]" />
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === "signup" && (
                <div>
                  <label htmlFor="name" className="label-text">{t("auth.name")}</label>
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t("auth.namePlaceholder")}
                    className="input-field"
                    autoComplete="name"
                  />
                </div>
              )}
              <div>
                <label htmlFor="email" className="label-text">{t("auth.email")}</label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("auth.emailPlaceholder")}
                  className="input-field"
                  autoComplete="email"
                />
              </div>
              <div>
                <label htmlFor="password" className="label-text">{t("auth.password")}</label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("auth.passwordPlaceholder")}
                  className="input-field"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
              </div>

              {error && (
                <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-500">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full" loading={submitting}>
                {mode === "login"
                  ? submitting ? t("auth.signingIn") : t("auth.signIn")
                  : submitting ? t("auth.creating") : t("auth.createAccount")}
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-[var(--muted)]">
              {mode === "login" ? t("auth.noAccount") : t("auth.haveAccount")}{" "}
              <button
                onClick={() => {
                  setMode(mode === "login" ? "signup" : "login");
                  setError(null);
                }}
                className="font-bold text-indigo-500 hover:underline dark:text-indigo-300"
              >
                {mode === "login" ? t("auth.signUpLink") : t("auth.loginLink")}
              </button>
            </p>
          </Card>

          <p className="mt-6 text-center text-xs text-[var(--muted)]">
            <Link href="/privacy" className="hover:underline">{t("footer.links.privacy")}</Link>
            {" · "}
            <Link href="/terms" className="hover:underline">{t("footer.links.terms")}</Link>
          </p>
        </motion.div>
      </main>
      <Footer />
    </div>
  );
}
