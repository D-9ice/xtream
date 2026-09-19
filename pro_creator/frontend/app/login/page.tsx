"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

function safeReturnPath(): string {
  const requestedNext = new URLSearchParams(window.location.search).get("next");
  if (
    requestedNext &&
    requestedNext.startsWith("/") &&
    !requestedNext.startsWith("//") &&
    !requestedNext.startsWith("/login")
  ) {
    return requestedNext;
  }
  return "/";
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const requestedMode = new URLSearchParams(window.location.search).get("mode");
    if (requestedMode === "register") {
      setMode("register");
    }
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response =
        mode === "register"
          ? await fetch(`${API_BASE}/auth/register`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email, password }),
            })
          : await fetch(`${API_BASE}/auth/login`, {
              method: "POST",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: new URLSearchParams({ username: email, password }),
            });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? (mode === "register" ? "Unable to create account" : "Invalid credentials"));
      }
      const data = await response.json();
      window.localStorage.setItem("pc_token", data.access_token);
      router.replace(safeReturnPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <main className="mx-auto flex max-w-md flex-col items-center px-6 py-20">
        <div className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-800 bg-slate-900/50 p-1">
            <button
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "signin" ? "bg-aurora text-slate-950" : "text-slate-300"}`}
              type="button"
              onClick={() => { setMode("signin"); setError(null); }}
            >
              Sign in
            </button>
            <button
              className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "register" ? "bg-aurora text-slate-950" : "text-slate-300"}`}
              type="button"
              onClick={() => { setMode("register"); setError(null); }}
            >
              Create account
            </button>
          </div>

          <h1 className="mt-6 text-2xl font-semibold text-white">
            {mode === "register" ? "Create your Pro Creator account" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            {mode === "register"
              ? "Create an account to subscribe, receive credits, and start producing."
              : "Sign in to access your projects, credits, and subscription."}
          </p>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white"
                type="email"
                aria-label="Email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="login-password">
                Password
              </label>
              <div className="relative mt-2">
                <input
                  id="login-password"
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 pr-12 text-sm text-white"
                  type={showPassword ? "text" : "password"}
                  aria-label="Password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  minLength={mode === "register" ? 8 : undefined}
                  required
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-3 flex items-center text-slate-400 transition hover:text-slate-200"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>
            <button
              className="w-full rounded-xl bg-aurora px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-aurora/90 disabled:opacity-60"
              type="submit"
              disabled={loading}
            >
              {loading
                ? mode === "register" ? "Creating account..." : "Signing in..."
                : mode === "register" ? "Create account & continue" : "Sign in"}
            </button>
          </form>

          {error ? (
            <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </p>
          ) : null}

          <button
            className="mt-5 w-full text-center text-xs text-slate-400 hover:text-slate-200"
            type="button"
            onClick={() => router.replace("/")}
          >
            Continue exploring Pro Creator Pro
          </button>
        </div>
      </main>
    </div>
  );
}