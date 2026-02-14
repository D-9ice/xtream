"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clearScript, importScript } from "../lib/api";

export default function ScriptActions({
  projectId,
  scriptText,
}: {
  projectId: string;
  scriptText: string;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastDeleted, setLastDeleted] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!scriptText.trim()) {
      setError("No script to delete.");
      return;
    }
    const confirmed = window.confirm(
      "Delete the script and scene metadata? This cannot be undone unless you restore it immediately."
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await clearScript({ project_id: projectId });
      setLastDeleted(scriptText);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setLoading(false);
    }
  };

  const handleUndo = async () => {
    if (!lastDeleted) {
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await importScript({ project_id: projectId, script: lastDeleted });
      setLastDeleted(null);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button
        className="rounded-full border border-red-500/40 px-3 py-1 text-[10px] text-red-200"
        type="button"
        onClick={handleDelete}
        disabled={loading}
      >
        {loading ? "Deleting..." : "Delete script"}
      </button>
      {lastDeleted ? (
        <button
          className="rounded-full border border-aurora/60 px-3 py-1 text-[10px] text-aurora"
          type="button"
          onClick={handleUndo}
          disabled={loading}
        >
          Undo delete
        </button>
      ) : null}
      {error ? (
        <span className="text-[10px] text-red-200">{error}</span>
      ) : null}
    </div>
  );
}
