"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";

import type { Clip, Project, Scene } from "../../../lib/api";
import {
  createEditorClip,
  deleteEditorClip,
  fetchEditorClips,
  fetchProject,
  fetchProjectScenes,
  fetchProjectScript,
  fetchArtifact,
  updateEditorClip,
} from "../../../lib/api";

type LipsyncCue = {
  start: number;
  end: number;
  viseme: string;
  word?: string;
  segment_id?: number | null;
};

  type LipsyncScene = {
    scene_id: number;
    source?: string;
    visemes?: LipsyncCue[];
  };

type LipsyncArtifact = {
  visemes?: LipsyncCue[];
    scenes?: LipsyncScene[];
  source?: string;
};

export default function EditorShell({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [script, setScript] = useState("");
  const [clips, setClips] = useState<Clip[]>([]);
  const [lipsync, setLipsync] = useState<LipsyncArtifact | null>(null);
  const [selectedLipsyncScene, setSelectedLipsyncScene] = useState<number | null>(null);
  const [scrubberTime, setScrubberTime] = useState(0);
  const [autoRefreshLipsync, setAutoRefreshLipsync] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const orderedClips = useMemo(
    () => [...clips].sort((a, b) => a.order_index - b.order_index),
    [clips]
  );

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [projectData, scenesData, scriptData, clipData] = await Promise.all([
          fetchProject(projectId),
          fetchProjectScenes(projectId),
          fetchProjectScript(projectId),
          fetchEditorClips(projectId),
        ]);
        let lipsyncData: LipsyncArtifact | null = null;
        try {
          lipsyncData = await fetchArtifact({
            project_id: projectId,
            artifact: "lipsync",
          });
        } catch {
          lipsyncData = null;
        }
        if (active) {
          setProject(projectData);
          setScenes(scenesData);
          setScript(scriptData);
          setClips(clipData);
          setLipsync(lipsyncData);
          const firstSceneId = lipsyncData?.scenes?.[0]?.scene_id ?? null;
          setSelectedLipsyncScene(firstSceneId);
          setScrubberTime(0);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load editor");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [projectId]);

  const handleAddClip = async (scene: Scene) => {
    try {
      const clip = await createEditorClip(projectId, {
        title: `Scene ${scene.id}`,
        start_time: 0,
        end_time: 10,
        order_index: orderedClips.length,
        notes: scene.text.slice(0, 160),
      });
      setClips((prev) => [...prev, clip]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add clip");
    }
  };

  const handleMoveClip = async (clip: Clip, direction: number) => {
    const index = orderedClips.findIndex((item) => item.id === clip.id);
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= orderedClips.length) {
      return;
    }
    const target = orderedClips[targetIndex];
    try {
      const [updatedClip, updatedTarget] = await Promise.all([
        updateEditorClip(projectId, clip.id, { order_index: target.order_index }),
        updateEditorClip(projectId, target.id, { order_index: clip.order_index }),
      ]);
      setClips((prev) =>
        prev.map((item) => {
          if (item.id === updatedClip.id) return updatedClip;
          if (item.id === updatedTarget.id) return updatedTarget;
          return item;
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reorder clip");
    }
  };

  const handleDeleteClip = async (clipId: number) => {
    try {
      await deleteEditorClip(projectId, clipId);
      setClips((prev) => prev.filter((item) => item.id !== clipId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete clip");
    }
  };

  const refreshLipsync = useCallback(async () => {
    try {
      const data = (await fetchArtifact({
        project_id: projectId,
        artifact: "lipsync",
      })) as LipsyncArtifact;
      setLipsync(data);
      const firstSceneId = data?.scenes?.[0]?.scene_id ?? null;
      setSelectedLipsyncScene((prev) => prev ?? firstSceneId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh lip sync");
    }
  }, [projectId]);

  const lipsyncScenes = lipsync?.scenes ?? [];
  const activeLipsyncScene =
    lipsyncScenes.find((scene) => scene.scene_id === selectedLipsyncScene) ??
    lipsyncScenes[0];
  const activeVisemes = activeLipsyncScene?.visemes ?? [];
  const timelineDuration =
    activeVisemes.length > 0 ? activeVisemes[activeVisemes.length - 1].end : 0;
  const currentViseme = activeVisemes.find(
    (cue) => scrubberTime >= cue.start && scrubberTime <= cue.end
  );

  useEffect(() => {
    if (!autoRefreshLipsync) {
      return;
    }
    const interval = setInterval(() => {
      refreshLipsync();
    }, 15000);
    return () => clearInterval(interval);
  }, [autoRefreshLipsync, refreshLipsync]);

  useEffect(() => {
    if (!isPlaying || timelineDuration <= 0) {
      return;
    }
    const tick = 0.1;
    const interval = setInterval(() => {
      setScrubberTime((prev) => {
        const next = prev + tick * playbackSpeed;
        if (next >= timelineDuration) {
          setIsPlaying(false);
          return timelineDuration;
        }
        return next;
      });
    }, tick * 1000);
    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, timelineDuration]);

  const downloadJson = (payload: object, filename: string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-midnight text-slate-100">
        <main className="mx-auto flex max-w-4xl items-center justify-center px-6 py-20">
          <p className="text-sm text-slate-400">Loading editor...</p>
        </main>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-midnight text-slate-100">
        <main className="mx-auto flex max-w-4xl items-center justify-center px-6 py-20">
          <p className="text-sm text-slate-400">Project not found.</p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
              Pro Creator Editor
            </p>
            <h1 className="text-3xl font-semibold text-white">
              {project.title}
            </h1>
            <p className="mt-2 text-sm text-slate-400">{project.topic}</p>
          </div>
          <Link
            className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora"
            href="/"
          >
            ← Back to Guided Studio
          </Link>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-10 lg:grid-cols-[2fr_1fr]">
        <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 lg:col-span-2">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Advanced Workspace
          </p>
          <p className="mt-2 text-sm text-slate-300">
            This editor is an advanced internal workspace. The normal production path should continue through the guided Create flow.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold">Timeline</h2>
              <p className="mt-2 text-sm text-slate-400">
                Arrange clips, trims, and cuts. Drag-and-drop support can be
                added after the first workflow is validated.
              </p>
            </div>
          </div>
          <div className="mt-6 space-y-3">
            {orderedClips.length === 0 ? (
              <p className="text-sm text-slate-400">No clips yet.</p>
            ) : (
              orderedClips.map((clip, index) => (
                <div
                  key={clip.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm"
                >
                  <div>
                    <p className="font-semibold">{clip.title}</p>
                    <p className="text-xs text-slate-400">
                      {clip.start_time}s → {clip.end_time}s
                    </p>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      className="rounded-md border border-slate-700 px-2 py-1"
                      type="button"
                      onClick={() => handleMoveClip(clip, -1)}
                      disabled={index === 0}
                    >
                      ↑
                    </button>
                    <button
                      className="rounded-md border border-slate-700 px-2 py-1"
                      type="button"
                      onClick={() => handleMoveClip(clip, 1)}
                      disabled={index === orderedClips.length - 1}
                    >
                      ↓
                    </button>
                    <button
                      className="rounded-md border border-red-500/40 px-2 py-1 text-red-200"
                      type="button"
                      onClick={() => handleDeleteClip(clip.id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-100">Lip sync timeline</p>
              <span className="text-[10px] uppercase tracking-wide text-slate-400">
                {lipsync?.source ? `Source: ${lipsync.source}` : "Source: unavailable"}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
              <button
                className="rounded-md border border-slate-700 px-2 py-1"
                type="button"
                onClick={() => setIsPlaying((prev) => !prev)}
                disabled={timelineDuration <= 0}
              >
                {isPlaying ? "Pause" : "Play"}
              </button>
              <label className="flex items-center gap-2">
                Speed
                <select
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[11px]"
                  value={playbackSpeed}
                  onChange={(event) => setPlaybackSpeed(Number(event.target.value))}
                >
                  <option value={0.5}>0.5x</option>
                  <option value={1}>1x</option>
                  <option value={1.5}>1.5x</option>
                  <option value={2}>2x</option>
                </select>
              </label>
              <button
                className="rounded-md border border-slate-700 px-2 py-1"
                type="button"
                onClick={() => {
                  setScrubberTime(0);
                  setIsPlaying(false);
                }}
              >
                Reset
              </button>
              <button
                className="rounded-md border border-slate-700 px-2 py-1"
                type="button"
                onClick={refreshLipsync}
              >
                Refresh
              </button>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={autoRefreshLipsync}
                  onChange={(event) => setAutoRefreshLipsync(event.target.checked)}
                />
                Auto-refresh
              </label>
              <button
                className="rounded-md border border-slate-700 px-2 py-1"
                type="button"
                onClick={() => downloadJson(lipsync ?? {}, "lipsync.json")}
                disabled={!lipsync}
              >
                Download JSON
              </button>
              {activeLipsyncScene ? (
                <button
                  className="rounded-md border border-slate-700 px-2 py-1"
                  type="button"
                  onClick={() =>
                    downloadJson(
                      activeLipsyncScene,
                      `lipsync_scene_${activeLipsyncScene.scene_id}.json`
                    )
                  }
                >
                  Download scene
                </button>
              ) : null}
            </div>
            {lipsyncScenes.length > 1 ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-[10px] uppercase tracking-wide text-slate-400">
                  Scene
                </span>
                <select
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                  value={selectedLipsyncScene ?? lipsyncScenes[0]?.scene_id ?? 1}
                  aria-label="Lip sync scene selection"
                  onChange={(event) =>
                    setSelectedLipsyncScene(Number(event.target.value))
                  }
                >
                  {lipsyncScenes.map((scene) => (
                    <option key={scene.scene_id} value={scene.scene_id}>
                      Scene {scene.scene_id}
                    </option>
                  ))}
                </select>
                <span className="text-[10px] text-slate-400">
                  {activeLipsyncScene?.source ?? "heuristic"}
                </span>
              </div>
            ) : null}
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span>0.0s</span>
                <span>{timelineDuration.toFixed(2)}s</span>
              </div>
              <input
                className="mt-2 w-full"
                type="range"
                min={0}
                max={timelineDuration || 1}
                step={0.05}
                value={scrubberTime}
                aria-label="Lip sync timeline scrubber"
                onChange={(event) => setScrubberTime(Number(event.target.value))}
              />
              <div className="mt-2 flex items-center justify-between text-xs text-slate-200">
                <span>Time: {scrubberTime.toFixed(2)}s</span>
                <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px]">
                  {currentViseme?.viseme ?? "REST"}
                </span>
              </div>
            </div>
            <div className="mt-3 max-h-36 space-y-2 overflow-auto text-xs text-slate-300">
              {activeVisemes.length > 0 ? (
                activeVisemes.slice(0, 12).map((cue, index) => (
                  <div key={`${cue.start}-${index}`} className="flex items-center justify-between">
                    <span>
                      {cue.start.toFixed(2)}s → {cue.end.toFixed(2)}s
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px]">
                      {cue.viseme || "REST"}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-400">
                  Generate voice to populate viseme cues.
                </p>
              )}
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
            <h3 className="text-lg font-semibold">Clip library</h3>
            <p className="mt-2 text-sm text-slate-400">
              Add generated scenes into your timeline.
            </p>
            <div className="mt-4 space-y-2 text-xs text-slate-300">
              {scenes.length === 0 ? (
                <p className="text-sm text-slate-400">No scenes yet.</p>
              ) : (
                scenes.map((scene) => (
                  <div
                    key={scene.id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2"
                  >
                    <span>Scene {scene.id}</span>
                    <button
                      className="rounded-md border border-aurora/40 px-2 py-1 text-[10px] text-aurora"
                      type="button"
                      onClick={() => handleAddClip(scene)}
                    >
                      Add
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
            <h3 className="text-lg font-semibold">Script reference</h3>
            <p className="mt-2 text-sm text-slate-400">
              Reference the full narration while arranging clips.
            </p>
            <div className="mt-3 max-h-64 overflow-auto whitespace-pre-line text-xs text-slate-300">
              {script || "No script yet."}
            </div>
          </div>

          {error ? (
            <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          ) : null}
        </aside>
      </main>
    </div>
  );
}
