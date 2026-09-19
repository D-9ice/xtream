"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  OrchestrationQueueItem,
  OrchestrationRunnerStatus,
  OrchestrationScheduleItem,
  Project,
} from "../../../lib/api";
import {
  deleteAllProjects,
  fetchAdminSubscriptions,
  fetchOrchestrationQueue,
  fetchOrchestrationRunnerStatus,
  fetchOrchestrationSchedules,
  fetchProjects,
  processOrchestrationQueue,
  purgeStaleProjects,
  retryOrchestrationJob,
  runOrchestrationSchedules,
  startOrchestrationRunner,
  stopOrchestrationRunner,
} from "../../../lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

type AccessState = "checking" | "ready" | "denied";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export default function InternalAdminPage() {
  const [accessState, setAccessState] = useState<AccessState>("checking");
  const [loading, setLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [queue, setQueue] = useState<OrchestrationQueueItem[]>([]);
  const [schedules, setSchedules] = useState<OrchestrationScheduleItem[]>([]);
  const [runner, setRunner] = useState<OrchestrationRunnerStatus | null>(null);
  const [purgeDays, setPurgeDays] = useState(30);

  const loadOperations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectRows, queueResponse, scheduleResponse, runnerStatus] = await Promise.all([
        fetchProjects(),
        fetchOrchestrationQueue(),
        fetchOrchestrationSchedules(),
        fetchOrchestrationRunnerStatus(),
      ]);
      setProjects(projectRows);
      setQueue(queueResponse.items);
      setSchedules(scheduleResponse.items);
      setRunner(runnerStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load operations data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    const verify = async () => {
      const ownerToken = window.localStorage.getItem("pc_token");
      const adminToken = window.sessionStorage.getItem("pc_admin_access_token");

      if (!ownerToken || !adminToken) {
        if (active) setAccessState("denied");
        return;
      }

      try {
        const [meResponse] = await Promise.all([
          globalThis.fetch(`${API_BASE}/auth/me`, {
            cache: "no-store",
            headers: { Authorization: `Bearer ${ownerToken}` },
          }),
          fetchAdminSubscriptions(),
        ]);

        const me = await meResponse.json().catch(() => null);
        if (!meResponse.ok || me?.role !== "admin") {
          throw new Error("Owner administration access required");
        }

        if (!active) return;
        setAccessState("ready");
        await loadOperations();
      } catch (err) {
        if (!active) return;
        setAccessState("denied");
        setError(err instanceof Error ? err.message : "Owner administration access required");
      }
    };

    void verify();
    return () => {
      active = false;
    };
  }, [loadOperations]);

  const queueStats = useMemo(() => {
    const pending = queue.filter((item) => item.status === "pending" || item.status === "queued").length;
    const running = queue.filter((item) => item.status === "running" || item.status === "processing").length;
    const failed = queue.filter((item) => item.status === "failed").length;
    return { pending, running, failed };
  }, [queue]);

  const runAction = useCallback(
    async (key: string, action: () => Promise<unknown>, successMessage: string) => {
      setBusyAction(key);
      setError(null);
      setMessage(null);
      try {
        await action();
        setMessage(successMessage);
        await loadOperations();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Operation failed");
      } finally {
        setBusyAction(null);
      }
    },
    [loadOperations]
  );

  const handlePurge = async () => {
    const days = Math.max(7, Math.floor(purgeDays || 30));
    if (!window.confirm(`Delete projects older than ${days} days? This cannot be undone.`)) {
      return;
    }
    await runAction(
      "purge",
      async () => purgeStaleProjects({ min_age_days: days }),
      `Stale projects older than ${days} days were purged.`
    );
  };

  const handleDeleteAll = async () => {
    const confirmation = window.prompt(
      'This permanently deletes every project record. Type DELETE ALL to continue.'
    );
    if (confirmation !== "DELETE ALL") {
      return;
    }
    await runAction("delete-all", deleteAllProjects, "All project records were deleted.");
  };

  if (accessState === "checking") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-midnight px-6 text-sm text-slate-400">
        Verifying owner operations access...
      </main>
    );
  }

  if (accessState === "denied") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-midnight px-6 py-20 text-slate-100">
        <section className="w-full max-w-xl rounded-3xl border border-slate-800 bg-slate-950/80 p-8 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
            Pro Creator Pro
          </p>
          <h1 className="mt-3 text-2xl font-semibold text-white">Owner access required</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            The Operations Console requires both the authenticated owner account and an active Admin Security Gate session.
          </p>
          {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
          <Link
            className="mt-6 inline-flex rounded-full border border-aurora/40 bg-aurora/10 px-5 py-2 text-sm font-semibold text-aurora"
            href="/admin"
          >
            Return to Admin Dashboard
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-midnight text-slate-100">
      <div className="mx-auto w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
        <header className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5 shadow-2xl shadow-black/20">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div className="flex min-w-0 items-center gap-4">
              <div
                aria-label="Pro Creator Pro"
                className="h-[82px] w-[240px] shrink-0 bg-[url('/procreator-sidebar-logo.webp')] bg-[length:228px_228px] bg-[position:center_calc(50%-9px)] bg-no-repeat"
                role="img"
              />
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Owner Administration
                </p>
                <h1 className="mt-1 text-2xl font-semibold text-white sm:text-3xl">
                  Operations Console
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                  Runtime operations for projects, orchestration, queues, schedules, and production diagnostics.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Link
                className="rounded-full border border-slate-700 bg-slate-900/70 px-4 py-2 text-xs font-semibold text-slate-200"
                href="/admin"
              >
                Admin Dashboard
              </Link>
              <Link
                className="rounded-full border border-slate-700 bg-slate-900/70 px-4 py-2 text-xs font-semibold text-slate-200"
                href="/"
              >
                Back to App
              </Link>
              <button
                className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora disabled:opacity-50"
                type="button"
                disabled={loading || busyAction !== null}
                onClick={() => void loadOperations()}
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
        </header>

        {message ? (
          <div className="mt-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Projects", projects.length],
            ["Queued / pending", queueStats.pending],
            ["Queue failures", queueStats.failed],
            ["Schedules", schedules.length],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl border border-slate-800 bg-slate-950/65 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-semibold text-white">{String(value)}</p>
            </div>
          ))}
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-2">
          <article className="rounded-3xl border border-slate-800 bg-slate-950/65 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Projects</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Project Operations</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Review registered projects and perform controlled cleanup without duplicating the public creation workflow.
                </p>
              </div>
              <span className="rounded-full border border-slate-700 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
                {projects.length} total
              </span>
            </div>

            <div className="mt-4 max-h-72 space-y-2 overflow-y-auto pr-1">
              {projects.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-500">
                  No project records are currently registered.
                </div>
              ) : (
                projects.slice(0, 12).map((project) => (
                  <div key={project.project_id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">{project.title || project.project_id}</p>
                        <p className="mt-1 truncate text-xs text-slate-500">{project.project_id}</p>
                      </div>
                      <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-slate-300">
                        {project.status}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-400">{project.topic || "No topic recorded"}</p>
                  </div>
                ))
              )}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
              <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Purge projects older than
                <div className="mt-2 flex items-center gap-2">
                  <input
                    className="w-24 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                    type="number"
                    min={7}
                    value={purgeDays}
                    onChange={(event) => setPurgeDays(Number(event.target.value))}
                  />
                  <span className="text-sm text-slate-400">days</span>
                </div>
              </label>
              <button
                className="self-end rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
                type="button"
                disabled={busyAction !== null}
                onClick={() => void handlePurge()}
              >
                {busyAction === "purge" ? "Purging..." : "Purge Stale"}
              </button>
            </div>

            <button
              className="mt-3 w-full rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 disabled:opacity-50"
              type="button"
              disabled={busyAction !== null || projects.length === 0}
              onClick={() => void handleDeleteAll()}
            >
              {busyAction === "delete-all" ? "Deleting..." : "Delete All Project Records"}
            </button>
          </article>

          <article className="rounded-3xl border border-slate-800 bg-slate-950/65 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Runtime</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Orchestration Runner</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Control queue processing and inspect the current orchestration runtime state.
                </p>
              </div>
              <span
                className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                  runner?.running
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
                    : "border-slate-700 bg-slate-900 text-slate-300"
                }`}
              >
                {runner?.running ? "Running" : "Stopped"}
              </span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Pending</p>
                <p className="mt-2 text-xl font-semibold text-white">{queueStats.pending}</p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Processing</p>
                <p className="mt-2 text-xl font-semibold text-white">{queueStats.running}</p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Failed</p>
                <p className="mt-2 text-xl font-semibold text-white">{queueStats.failed}</p>
              </div>
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <button
                className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50"
                type="button"
                disabled={busyAction !== null || Boolean(runner?.running)}
                onClick={() =>
                  void runAction(
                    "runner-start",
                    async () => startOrchestrationRunner({ interval_seconds: runner?.interval_seconds || 5 }),
                    "Orchestration runner started."
                  )
                }
              >
                {busyAction === "runner-start" ? "Starting..." : "Start Runner"}
              </button>
              <button
                className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-semibold text-slate-200 disabled:opacity-50"
                type="button"
                disabled={busyAction !== null || !runner?.running}
                onClick={() =>
                  void runAction("runner-stop", stopOrchestrationRunner, "Orchestration runner stopped.")
                }
              >
                {busyAction === "runner-stop" ? "Stopping..." : "Stop Runner"}
              </button>
              <button
                className="rounded-xl border border-aurora/40 bg-aurora/10 px-3 py-2 text-sm font-semibold text-aurora disabled:opacity-50"
                type="button"
                disabled={busyAction !== null || queueStats.pending === 0}
                onClick={() =>
                  void runAction(
                    "process-one",
                    async () => processOrchestrationQueue({ limit: 1 }),
                    "Processed the next queued job."
                  )
                }
              >
                {busyAction === "process-one" ? "Processing..." : "Process Next"}
              </button>
            </div>

            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-400">
              Runner interval: <span className="font-semibold text-slate-200">{runner?.interval_seconds ?? "—"} seconds</span>
              {runner?.detail ? <p className="mt-2">{runner.detail}</p> : null}
            </div>
          </article>
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-2">
          <article className="rounded-3xl border border-slate-800 bg-slate-950/65 p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Queue</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Recent Jobs</h2>
              </div>
              <span className="text-xs text-slate-500">{queue.length} records</span>
            </div>
            <div className="mt-4 max-h-80 space-y-2 overflow-y-auto pr-1">
              {queue.length === 0 ? (
                <p className="text-sm text-slate-500">No orchestration jobs are currently recorded.</p>
              ) : (
                queue.slice(0, 15).map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-white">{item.kind}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.project_id}</p>
                      </div>
                      <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-slate-300">
                        {item.status}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-500">
                      <span>Attempts {item.attempts}/{item.max_attempts}</span>
                      {item.status === "failed" ? (
                        <button
                          className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-2 py-1 font-semibold text-amber-100 disabled:opacity-50"
                          type="button"
                          disabled={busyAction !== null}
                          onClick={() =>
                            void runAction(
                              `retry-${item.id}`,
                              async () => retryOrchestrationJob(item.id),
                              `Job ${item.id} returned to the queue.`
                            )
                          }
                        >
                          {busyAction === `retry-${item.id}` ? "Retrying..." : "Retry"}
                        </button>
                      ) : (
                        <span>{formatDate(item.updated_at)}</span>
                      )}
                    </div>
                    {item.last_error ? <p className="mt-2 text-xs text-rose-300">{item.last_error}</p> : null}
                  </div>
                ))
              )}
            </div>
          </article>

          <article className="rounded-3xl border border-slate-800 bg-slate-950/65 p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Automation</p>
                <h2 className="mt-1 text-xl font-semibold text-white">Schedules</h2>
              </div>
              <button
                className="rounded-full border border-aurora/40 bg-aurora/10 px-3 py-1.5 text-xs font-semibold text-aurora disabled:opacity-50"
                type="button"
                disabled={busyAction !== null || schedules.length === 0}
                onClick={() =>
                  void runAction("run-schedules", runOrchestrationSchedules, "Eligible schedules were evaluated.")
                }
              >
                {busyAction === "run-schedules" ? "Running..." : "Run Due Schedules"}
              </button>
            </div>
            <div className="mt-4 max-h-80 space-y-2 overflow-y-auto pr-1">
              {schedules.length === 0 ? (
                <p className="text-sm text-slate-500">No orchestration schedules are currently configured.</p>
              ) : (
                schedules.slice(0, 15).map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-white">{item.project_id}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          Every {item.cadence_days} day{item.cadence_days === 1 ? "" : "s"}
                        </p>
                      </div>
                      <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-slate-300">
                        {item.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-400">Next run: {formatDate(item.next_run_at)}</p>
                    <p className="mt-1 text-xs text-slate-500">Last run: {formatDate(item.last_run_at)}</p>
                  </div>
                ))
              )}
            </div>
          </article>
        </section>

        <footer className="mt-5 rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-3 text-xs text-slate-500">
          Owner-only operations surface. Public creation, subscription, and user-facing production controls remain in the main Pro Creator Pro application.
        </footer>
      </div>
    </main>
  );
}
