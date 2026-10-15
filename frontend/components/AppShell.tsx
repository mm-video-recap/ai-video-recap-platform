"use client";

import type { ReactNode } from "react";
import Navbar from "@/components/Navbar";
import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import Footer from "@/components/Footer";

/** Layout shell for authenticated app pages: top nav + sidebar + bottom nav (mobile). */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <div className="flex flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 px-4 pb-28 pt-6 sm:px-6 md:pb-10">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
      <div className="hidden md:block">
        <Footer />
      </div>
      <BottomNav />
    </div>
  );
}
