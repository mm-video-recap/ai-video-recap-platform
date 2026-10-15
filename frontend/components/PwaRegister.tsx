"use client";

import { useEffect } from "react";

/** Register the minimal offline-shell service worker (non-blocking). */
export default function PwaRegister() {
  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !("serviceWorker" in navigator) ||
      process.env.NODE_ENV !== "production"
    ) {
      return;
    }
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      /* service worker is optional */
    });
  }, []);
  return null;
}
