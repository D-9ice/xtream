"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Project } from "../lib/api";
import { clearScript, deleteProject, fetchProjectScript } from "../lib/api";

export default function ProjectCard({
  project,
  onScriptCleared,
  onProjectDeleted,
  scriptRefreshToken,
}: {
  project: Project;
  onScriptCleared?: () => void;
  onProjectDeleted?: (projectId: string) => void;
  scriptRefreshToken?: number;
}) {
  const router = useRouter();
  const [clearing, setClearing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasScript, setHasScript] = useState(false);

  useEffect(() => {
    let active = true;
    const loadScript = async () => {
      try {
        const script = await fetchProjectScript(project.project_id);
        if (active) {
          setHasScript(script.trim().length > 0);
        }
      } catch {
        if (active) {
          setHasScript(false);
        }
      }
    };
    loadScript();
    return () => {
      active = false;
    };
  }, [project.project_id, scriptRefreshToken]);

  const handleClearScript = async () => {
    const confirmed = window.confirm(
      "Clear the script for this project? This removes script and scenes."
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setClearing(true);
    try {
      await clearScript({ project_id: project.project_id });
      setHasScript(false);
      onScriptCleared?.();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clear failed");
    } finally {
      setClearing(false);
    }
  };

  const handleDeleteProject = async () => {
    const confirmed = window.confirm(
      "Delete this project and all its assets? This cannot be undone."
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setDeleting(true);
    try {
      await deleteProject(project.project_id);
      onProjectDeleted?.(project.project_id);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-900/60 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">{project.title}</h3>
          <p className="text-sm text-slate-400">{project.topic}</p>
        </div>
        <span className="rounded-full bg-aurora/20 px-3 py-1 text-xs uppercase tracking-wide text-aurora">
          {project.status}
        </span>
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Created: {new Date(project.created_at).toLocaleString()}
      </p>
      <p className="mt-2 text-xs text-slate-500">ID: {project.project_id}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <a
          className="inline-flex items-center text-xs font-semibold text-aurora hover:text-aurora/80"
          href={`/projects/${project.project_id}`}
        >
          View details →
        </a>
        {hasScript ? (
          <button
            className="rounded-full border border-red-500/40 px-3 py-1 text-[10px] text-red-200"
            type="button"
            onClick={handleClearScript}
            disabled={clearing || deleting}
          >
            {clearing ? "Clearing..." : "Clear script"}
          </button>
        ) : null}
        <button
          className="rounded-full border border-red-500/40 px-3 py-1 text-[10px] text-red-200"
          type="button"
          onClick={handleDeleteProject}
          disabled={clearing || deleting}
        >
          {deleting ? "Deleting..." : "Delete project"}
        </button>
        {error ? (
          <span className="text-[10px] text-red-200">{error}</span>
        ) : null}
      </div>
    </div>
  );
}
