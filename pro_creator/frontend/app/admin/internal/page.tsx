"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import LegacyDashboard from "../../page.clean";

export default function InternalAdminPage() {
  const [hasAccess, setHasAccess] = useState(false);
  const [checkedAccess, setCheckedAccess] = useState(false);

  useEffect(() => {
    const token = window.sessionStorage.getItem("pc_admin_access_token");
    setHasAccess(Boolean(token));
    setCheckedAccess(true);
  }, []);

  if (!checkedAccess) {
    return (
      <main className="mx-auto flex min-h-screen max-w-4xl items-center justify-center px-6 py-20 text-sm text-slate-400">
        Loading internal tools...
      </main>
    );
  }

  if (!hasAccess) {
    return (
      <div className="min-h-screen bg-midnight text-slate-100">
        <main className="mx-auto flex min-h-screen max-w-3xl items-center justify-center px-6 py-20">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-8 text-center">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Internal Tools
            </p>
            <h1 className="mt-3 text-2xl font-semibold text-white">
              Admin access required
            </h1>
            <p className="mt-3 text-sm text-slate-300">
              This legacy dashboard is restricted to internal admin use.
            </p>
            <Link
              className="mt-5 inline-flex rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
              href="/admin"
            >
              Open Admin Access
            </Link>
          </section>
        </main>
      </div>
    );
  }

  return <LegacyDashboard />;
}
