"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

type GuardState = "checking" | "allowed" | "error";

function loginDestination(): string {
  if (typeof window === "undefined") {
    return "/login";
  }
  const next = `${window.location.pathname}${window.location.search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

function clearExpiredAuth(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem("pc_token");
  window.sessionStorage.removeItem("pc_admin_access_token");
  window.localStorage.removeItem("pc_admin_access_token");
}

export default function AuthGateGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === "/login";
  const [state, setState] = useState<GuardState>(isLoginPage ? "allowed" : "checking");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isLoginPage) {
      setState("allowed");
      setMessage(null);
      return;
    }

    let active = true;
    const controller = new AbortController();

    const verifyAccess = async () => {
      setState("checking");
      setMessage(null);

      try {
        const gateResponse = await globalThis.fetch(`${API_BASE}/auth/gate/status`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!gateResponse.ok) {
          throw new Error("Unable to verify authentication status.");
        }

        const gate = (await gateResponse.json()) as { enabled?: boolean };
        if (!gate.enabled) {
          if (active) {
            setState("allowed");
          }
          return;
        }

        const token = window.localStorage.getItem("pc_token");
        if (!token) {
          if (active) {
            router.replace(loginDestination());
          }
          return;
        }

        const meResponse = await globalThis.fetch(`${API_BASE}/auth/me`, {
          cache: "no-store",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          signal: controller.signal,
        });

        if (meResponse.status === 401 || meResponse.status === 403) {
          clearExpiredAuth();
          if (active) {
            router.replace(loginDestination());
          }
          return;
        }

        if (!meResponse.ok) {
          throw new Error("Unable to validate the current session.");
        }

        if (active) {
          setState("allowed");
        }
      } catch (error) {
        if (controller.signal.aborted || !active) {
          return;
        }
        setMessage(error instanceof Error ? error.message : "Unable to validate the current session.");
        setState("error");
      }
    };

    void verifyAccess();

    return () => {
      active = false;
      controller.abort();
    };
  }, [isLoginPage, pathname, router]);

  if (isLoginPage || state === "allowed") {
    return <>{children}</>;
  }

  if (state === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-midnight px-6 text-slate-100">
        <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-950/80 p-6 text-center">
          <h1 className="text-xl font-semibold text-white">Authentication unavailable</h1>
          <p className="mt-3 text-sm text-slate-400">{message}</p>
          <button
            className="mt-5 rounded-xl border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
            type="button"
            onClick={() => window.location.reload()}
          >
            Retry
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-midnight px-6 text-slate-100">
      <p className="text-sm text-slate-400">Verifying session...</p>
    </main>
  );
}
