"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  enqueueOrchestrationJob,
  fetchMyCredits,
  fetchOrchestrationRunnerStatus,
  startOrchestrationRunner,
  stopOrchestrationRunner,
  CreditBalance,
  OrchestrationRunnerStatus,
} from "../../lib/api";

const FACTORY_MODE_ENABLED = process.env.NEXT_PUBLIC_FACTORY_MODE_ENABLED === "true";

function factoryModeAccessIsActive(summary: CreditBalance | null): boolean {
  if (!summary) {
    return false;
  }
  if (summary.owner_mode_enabled) {
    return true;
  }
  if (summary.factory_mode_status !== "active") {
    return false;
  }
  if ((summary.factory_mode_access ?? "none") !== "subscription") {
    return true;
  }
  if (!summary.factory_mode_renewal_date) {
    return false;
  }
  const renewalAt = Date.parse(summary.factory_mode_renewal_date);
  if (Number.isNaN(renewalAt)) {
    return false;
  }
  return renewalAt > Date.now();
}

export default function FactoryModePage() {
  const router = useRouter();
  const [credits, setCredits] = useState<CreditBalance | null>(null);
  const [queue, setQueue] = useState("Launch title one\nLaunch title two");
  const [runnerStatus, setRunnerStatus] = useState<OrchestrationRunnerStatus | null>(null);
  const [busy, setBusy] = useState<"start" | "stop" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const queueTitles = useMemo(
    () =>
      queue
        .split(/\r?\n/)
        .map((title) => title.trim())
        .filter(Boolean),
    [queue]
  );

  const ownerModeEnabled = Boolean(credits?.owner_mode_enabled);
  const factoryModeActive = factoryModeAccessIsActive(
    credits ? { ...credits, owner_mode_enabled: ownerModeEnabled } : credits
  );
  const factoryModeDeploymentEnabled = FACTORY_MODE_ENABLED || ownerModeEnabled;

  useEffect(() => {
    let active = true;
    const loadState = async () => {
      try {
        const [nextCredits, nextRunner] = await Promise.all([
          fetchMyCredits(),
          fetchOrchestrationRunnerStatus(),
        ]);
        if (!active) {
          return;
        }
        setCredits(nextCredits);
        setRunnerStatus(nextRunner);
      } catch {
        if (active) {
          setCredits(null);
          setRunnerStatus(null);
        }
      }
    };
    void loadState();
    return () => {
      active = false;
    };
  }, []);

  async function handleStart() {
    if (!factoryModeActive) {
      return;
    }
    if (queueTitles.length === 0) {
      setError("Add at least one title to the factory queue.");
      setMessage(null);
      return;
    }
    setBusy("start");
    setError(null);
    setMessage(null);
    try {
      await enqueueOrchestrationJob({
        project_id: "factory-mode",
        kind: "factory_mode",
        titles: queueTitles,
        publish_message: queueTitles[0],
      });
      try {
        const runner = await startOrchestrationRunner({ interval_seconds: 5 });
        setRunnerStatus(runner);
      } catch {
        // Deployed workers can manage the queue independently.
      }
      setRunnerStatus((current) => current ?? { enabled: true, running: true, interval_seconds: 5, detail: null });
      setMessage(`Queued ${queueTitles.length} title${queueTitles.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Factory Mode");
    } finally {
      setBusy(null);
    }
  }

  async function handleStop() {
    if (!factoryModeDeploymentEnabled) {
      return;
    }
    setBusy("stop");
    setError(null);
    try {
      const runner = await stopOrchestrationRunner();
      setRunnerStatus(runner);
      setMessage("Factory runner paused.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop Factory Mode");
    } finally {
      setBusy(null);
    }
  }

  const runnerChipState = !factoryModeDeploymentEnabled || !factoryModeActive
    ? "locked"
    : runnerStatus?.running
      ? "runner"
      : "ready";
  const runnerChip = runnerChipState === "runner" ? "Runner live" : runnerChipState === "ready" ? "Ready" : "Locked";
  const runnerChipStyles =
    runnerChipState === "runner"
      ? "border-[#28c840] bg-[#28c840] text-slate-950 shadow-[0_0_18px_rgba(40,200,64,0.45)]"
      : runnerChipState === "ready"
        ? "border-[#ffbd2e] bg-[#ffbd2e] text-slate-950 shadow-[0_0_18px_rgba(255,189,46,0.45)]"
        : "border-[#ff5f57] bg-[#ff5f57] text-slate-950 shadow-[0_0_18px_rgba(255,95,87,0.45)]";

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex items-start justify-between gap-4 rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Autonomous production</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">Factory Mode</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Continuous video production and distribution to connected social platforms.
            </p>
          </div>
          <div className="flex flex-col items-end gap-3">
            <div
              className={`rounded-full px-3 py-2 text-xs uppercase tracking-[0.2em] ${runnerChipStyles}`}
            >
              {runnerChip}
            </div>
            <Link
              className="rounded-full border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
              href="/"
            >
              Back to app
            </Link>
          </div>
        </div>

        {!factoryModeDeploymentEnabled ? (
          <div className="rounded-2xl border border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
            Factory Mode is locked until this deployment sets{" "}
            <span className="font-semibold text-slate-200">NEXT_PUBLIC_FACTORY_MODE_ENABLED=true</span>.
            <button
              className="mt-4 inline-flex rounded-full border border-amber-300/40 bg-amber-300/10 px-4 py-2 text-sm font-semibold text-amber-50 transition hover:border-amber-200/60 hover:bg-amber-300/15"
              type="button"
              onClick={() => router.push("/?credits=1")}
            >
              Open Credits & Plans
            </button>
          </div>
        ) : factoryModeActive ? (
          <section className="grid gap-6 lg:grid-cols-[1fr_auto]">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Factory queue</p>
              <p className="mt-3 leading-6 text-slate-300">
                Add one title per line. Factory Mode will generate each project in order, then publish each finished
                video to every connected platform until titles or credits run out.
              </p>
              <textarea
                className="mt-4 min-h-[10rem] w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-200 outline-none transition placeholder:text-slate-500 focus:border-aurora/50"
                placeholder="Launch title one&#10;Launch title two&#10;Launch title three"
                value={queue}
                onChange={(event) => setQueue(event.target.value)}
              />
              {message ? <p className="mt-3 text-sm text-aurora">{message}</p> : null}
              {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
              <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                The queue is processed in order and published to every connected platform.
              </p>
            </div>
            <div className="space-y-[3px]">
              <button
                className="w-full rounded-2xl border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-900/55 disabled:text-slate-500"
                type="button"
                disabled={busy === "start" || queueTitles.length === 0}
                onClick={handleStart}
              >
                Start factory run
              </button>
              <button
                className="w-full rounded-2xl border border-slate-800 bg-slate-900/55 px-5 py-3 text-sm font-semibold text-slate-300 disabled:cursor-not-allowed disabled:text-slate-500"
                type="button"
                disabled={busy === "stop"}
                onClick={handleStop}
              >
                Stop run
              </button>
            </div>
          </section>
        ) : (
          <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-6">
            <p className="text-xs uppercase tracking-[0.25em] text-amber-100/80">Access required</p>
            <h2 className="mt-2 text-lg font-semibold text-white">Unlock Factory Mode</h2>
            <p className="mt-2 max-w-2xl text-sm text-amber-50/80">
              Factory Mode is deployed but locked until you activate a subscription in Credits & Plans.
            </p>
            <button
              className="mt-4 inline-flex rounded-full border border-amber-300/40 bg-amber-300/10 px-4 py-2 text-sm font-semibold text-amber-50"
              type="button"
              onClick={() => router.push("/?credits=1")}
            >
              Open Credits & Plans
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
