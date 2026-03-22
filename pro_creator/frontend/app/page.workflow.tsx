"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  WorkflowCharacterList,
  WorkflowLibrary,
  WorkflowProject,
  WorkflowState,
  approveWorkflowCharacters,
  approveWorkflowScript,
  createWorkflowCharacter,
  createWorkflowProject,
  fetchMyCredits,
  fetchWorkflowCharacters,
  fetchWorkflowLibrary,
  fetchWorkflowProductionSummary,
  fetchWorkflowProject,
  fetchWorkflowProjects,
  generateWorkflowCharacter,
  generateWorkflowScript,
  regenerateWorkflowScript,
  selectWorkflowCharacters,
  startWorkflowProduction,
  updateWorkflowScript,
  uploadWorkflowCharacter,
} from "../lib/api";

type NavItem = "overview" | "projects" | "create" | "library";
type LibraryTab = "characters" | "scripts" | "videos";

const NAV_ITEMS: Array<{ id: NavItem; label: string; detail: string }> = [
  { id: "overview", label: "Overview", detail: "Current progress and quick continue" },
  { id: "projects", label: "Projects", detail: "Open and manage your work" },
  { id: "create", label: "Create", detail: "Guided story to video workflow" },
  { id: "library", label: "Library", detail: "Characters, scripts, and videos" },
];

const STEPS = [
  "Story Request",
  "Review Script",
  "Choose Characters",
  "Produce Video",
];

function workflowStageIndex(project: WorkflowProject | null): number {
  if (!project) {
    return 0;
  }
  const state = project.workflow_state;
  if (
    state === "production_ready" ||
    state === "production_queued" ||
    state === "production_running" ||
    state === "video_completed" ||
    state === "production_failed" ||
    state === "characters_approved"
  ) {
    return state === "characters_approved" ? 2 : 3;
  }
  if (state === "characters_in_progress" || project.character_package_approved) {
    return 2;
  }
  if (state === "script_approved") {
    return 2;
  }
  if (state === "script_generated") {
    return 1;
  }
  return 0;
}

function workflowStageLabel(state: WorkflowState): string {
  switch (state) {
    case "draft":
      return "Idea entered";
    case "script_generating":
      return "Script generating";
    case "script_generated":
      return "Script generated";
    case "script_approved":
      return "Script approved";
    case "characters_in_progress":
      return "Characters in progress";
    case "characters_approved":
      return "Characters approved";
    case "production_ready":
      return "Production ready";
    case "production_queued":
      return "Production queued";
    case "production_running":
      return "Production running";
    case "video_completed":
      return "Video completed";
    case "production_failed":
      return "Production failed";
  }
}

function stageUnlocked(project: WorkflowProject | null, stageIndex: number): boolean {
  if (!project) {
    return stageIndex === 0;
  }
  if (stageIndex === 0) return true;
  if (stageIndex === 1) {
    return Boolean((project.script_draft || "").trim()) || project.workflow_state === "script_generating";
  }
  if (stageIndex === 2) {
    return Boolean((project.script_approved || "").trim()) || project.workflow_state === "script_approved";
  }
  if (stageIndex === 3) {
    return project.character_package_approved;
  }
  return false;
}

function stageTone(project: WorkflowProject | null, stageIndex: number): string {
  if (!project) {
    return stageIndex === 0 ? "active" : "locked";
  }
  const current = workflowStageIndex(project);
  if (stageIndex < current) return "complete";
  if (stageIndex === current) return "active";
  if (stageUnlocked(project, stageIndex)) return "ready";
  return "locked";
}

function toneClasses(tone: string): string {
  switch (tone) {
    case "complete":
      return "border-emerald-400/40 bg-emerald-400/10 text-emerald-100";
    case "active":
      return "border-aurora/50 bg-aurora/10 text-white shadow-[0_0_0_1px_rgba(34,211,238,0.18)]";
    case "ready":
      return "border-amber-400/35 bg-amber-400/10 text-amber-100";
    default:
      return "border-slate-800 bg-slate-900/60 text-slate-500";
  }
}

function statusPill(state: WorkflowState): string {
  if (state === "video_completed") return "bg-emerald-400/15 text-emerald-200";
  if (state === "production_failed") return "bg-red-500/15 text-red-200";
  if (state === "production_running" || state === "production_queued") {
    return "bg-amber-400/15 text-amber-100";
  }
  return "bg-aurora/15 text-aurora";
}

export default function WorkflowHomePage() {
  const [activeNav, setActiveNav] = useState<NavItem>("create");
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("characters");
  const [projects, setProjects] = useState<WorkflowProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<WorkflowProject | null>(null);
  const [characters, setCharacters] = useState<WorkflowCharacterList | null>(null);
  const [library, setLibrary] = useState<WorkflowLibrary | null>(null);
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [productionEstimate, setProductionEstimate] = useState<number>(20);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [titleInput, setTitleInput] = useState("");
  const [ideaInput, setIdeaInput] = useState("");
  const [genreInput, setGenreInput] = useState("");
  const [durationInput, setDurationInput] = useState(3);
  const [toneInput, setToneInput] = useState("cinematic");
  const [scriptInput, setScriptInput] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [characterRole, setCharacterRole] = useState("main");
  const [characterDescription, setCharacterDescription] = useState("");
  const [characterTraits, setCharacterTraits] = useState("");
  const [characterVoice, setCharacterVoice] = useState("default");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const selectedStage = workflowStageIndex(selectedProject);
  const activeProject = selectedProject ?? projects[0] ?? null;

  const approvedScripts = useMemo(
    () => (library?.scripts ?? projects.filter((project) => Boolean((project.script_approved || "").trim()))),
    [library, projects]
  );
  const completedVideos = useMemo(
    () => (library?.videos ?? projects.filter((project) => Boolean((project.final_video_url || "").trim()))),
    [library, projects]
  );

  async function refreshProjects(nextSelectedId?: string | null) {
    const [workflowProjects, credits, workflowLibrary] = await Promise.all([
      fetchWorkflowProjects(),
      fetchMyCredits().catch(() => null),
      fetchWorkflowLibrary().catch(() => null),
    ]);
    setProjects(workflowProjects);
    setCreditBalance(credits?.credits_balance ?? null);
    setLibrary(workflowLibrary);

    const preferredId =
      nextSelectedId ??
      selectedProjectId ??
      workflowProjects[0]?.project_id ??
      null;
    if (preferredId) {
      setSelectedProjectId(preferredId);
    } else {
      setSelectedProjectId(null);
      setSelectedProject(null);
      setCharacters(null);
    }
  }

  async function refreshProject(projectId: string) {
    const [project, nextCharacters, summary] = await Promise.all([
      fetchWorkflowProject(projectId),
      fetchWorkflowCharacters(projectId).catch(() => null),
      fetchWorkflowProductionSummary(projectId).catch(() => null),
    ]);
    setSelectedProject(project);
    setCharacters(nextCharacters);
    setScriptInput(project.script_draft || project.script_approved || "");
    setTitleInput(project.title || "");
    setIdeaInput(project.idea_prompt || "");
    setGenreInput(project.genre || "");
    setDurationInput(project.target_duration_minutes || 3);
    setProductionEstimate(summary?.estimated_credits ?? 20);
    if (summary?.current_credit_balance !== undefined) {
      setCreditBalance(summary.current_credit_balance);
    }
  }

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        await refreshProjects(null);
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load workflow");
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
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    let active = true;
    const loadProject = async () => {
      try {
        await refreshProject(selectedProjectId);
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load project");
        }
      }
    };
    loadProject();
    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  async function afterProjectMutation(projectId: string, message: string) {
    await refreshProjects(projectId);
    await refreshProject(projectId);
    setStatus(message);
    setError(null);
  }

  async function handleGenerateScript(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("script");
    setError(null);
    setStatus(null);
    try {
      let projectId = selectedProjectId;
      if (!projectId) {
        const created = await createWorkflowProject({
          title: titleInput,
          idea_prompt: ideaInput,
          genre: genreInput,
          target_duration_minutes: durationInput,
        });
        projectId = created.project_id;
      }
      const updated = await generateWorkflowScript(projectId, {
        title: titleInput,
        idea_prompt: ideaInput,
        genre: genreInput,
        target_duration_minutes: durationInput,
        tone: toneInput,
      });
      setActiveNav("create");
      await afterProjectMutation(updated.project_id, "Script draft is ready for review.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate script");
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveScript() {
    if (!selectedProject) return;
    setBusy("save-script");
    setError(null);
    setStatus(null);
    try {
      const updated = await updateWorkflowScript(selectedProject.project_id, {
        script: scriptInput,
        update_scenes: true,
      });
      await afterProjectMutation(
        updated.project_id,
        "Script draft updated. Approval gates will require confirmation again."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save script");
    } finally {
      setBusy(null);
    }
  }

  async function handleApproveScript() {
    if (!selectedProject) return;
    setBusy("approve-script");
    setError(null);
    setStatus(null);
    try {
      const updated = await approveWorkflowScript(selectedProject.project_id);
      await afterProjectMutation(updated.project_id, "Script approved. Character selection is now unlocked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve script");
    } finally {
      setBusy(null);
    }
  }

  async function handleRegenerateScript() {
    if (!selectedProject) return;
    setBusy("regenerate-script");
    setError(null);
    setStatus(null);
    try {
      const updated = await regenerateWorkflowScript(selectedProject.project_id, {
        title: titleInput,
        idea_prompt: ideaInput,
        genre: genreInput,
        target_duration_minutes: durationInput,
        tone: toneInput,
      });
      await afterProjectMutation(updated.project_id, "A new script draft has been generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to regenerate script");
    } finally {
      setBusy(null);
    }
  }

  async function toggleCharacter(characterId: string) {
    if (!selectedProject || !characters) return;
    setBusy(`character-${characterId}`);
    setError(null);
    setStatus(null);
    try {
      const selected = characters.selected_character_ids.includes(characterId)
        ? characters.selected_character_ids.filter((item) => item !== characterId)
        : [...characters.selected_character_ids, characterId];
      const next = await selectWorkflowCharacters(selectedProject.project_id, selected);
      setCharacters(next);
      await refreshProjects(selectedProject.project_id);
      await refreshProject(selectedProject.project_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update character selection");
    } finally {
      setBusy(null);
    }
  }

  async function handleCreateCharacter(mode: "manual" | "generate" | "upload") {
    if (!selectedProject) return;
    setBusy(`character-${mode}`);
    setError(null);
    setStatus(null);
    try {
      const traits = characterTraits
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      let nextCharacters: WorkflowCharacterList;
      if (mode === "generate") {
        nextCharacters = await generateWorkflowCharacter(selectedProject.project_id, {
          name: characterName,
          role_type: characterRole,
          description: characterDescription,
          personality_traits: traits,
          voice_profile: characterVoice,
          style: "cinematic",
          select_after_create: true,
        });
      } else if (mode === "upload") {
        if (!uploadFile) {
          throw new Error("Choose a reference image before uploading");
        }
        nextCharacters = await uploadWorkflowCharacter(selectedProject.project_id, {
          file: uploadFile,
          name: characterName,
          role_type: characterRole,
          description: characterDescription,
          voice_profile: characterVoice,
          select_after_create: true,
        });
      } else {
        nextCharacters = await createWorkflowCharacter(selectedProject.project_id, {
          name: characterName,
          role_type: characterRole,
          description: characterDescription,
          reference_image_url: referenceUrl,
          personality_traits: traits,
          voice_profile: characterVoice,
          select_after_create: true,
        });
      }
      setCharacters(nextCharacters);
      setCharacterName("");
      setCharacterDescription("");
      setCharacterTraits("");
      setReferenceUrl("");
      setUploadFile(null);
      await refreshProjects(selectedProject.project_id);
      await refreshProject(selectedProject.project_id);
      setStatus("Character added to the project cast.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create character");
    } finally {
      setBusy(null);
    }
  }

  async function handleApproveCharacters() {
    if (!selectedProject || !characters) return;
    setBusy("approve-characters");
    setError(null);
    setStatus(null);
    try {
      const next = await approveWorkflowCharacters(
        selectedProject.project_id,
        characters.selected_character_ids
      );
      setCharacters(next);
      await refreshProjects(selectedProject.project_id);
      await refreshProject(selectedProject.project_id);
      setStatus("Characters approved. Video production is now unlocked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve characters");
    } finally {
      setBusy(null);
    }
  }

  async function handleStartProduction() {
    if (!selectedProject) return;
    setBusy("start-production");
    setError(null);
    setStatus(null);
    try {
      const response = await startWorkflowProduction(selectedProject.project_id);
      await afterProjectMutation(
        response.project.project_id,
        response.video_path
          ? "Video production completed."
          : "Video production started."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start production");
    } finally {
      setBusy(null);
    }
  }

  function renderOverview() {
    return (
      <section className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
            <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
              Active Project
            </p>
            {activeProject ? (
              <>
                <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-2xl font-semibold text-white">
                      {activeProject.title}
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm text-slate-400">
                      {activeProject.idea_prompt || activeProject.topic}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs ${statusPill(activeProject.workflow_state)}`}>
                    {workflowStageLabel(activeProject.workflow_state)}
                  </span>
                </div>
                <div className="mt-6 flex flex-wrap gap-3">
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                    type="button"
                    onClick={() => {
                      setSelectedProjectId(activeProject.project_id);
                      setActiveNav("create");
                    }}
                  >
                    Continue Project
                  </button>
                  <button
                    className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-300"
                    type="button"
                    onClick={() => setActiveNav("projects")}
                  >
                    View All Projects
                  </button>
                </div>
              </>
            ) : (
              <div className="mt-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/60 p-6">
                <p className="text-sm text-slate-300">
                  No project is active yet. Start from the Create screen to generate your first script.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                Workflow Progress
              </p>
              <div className="mt-4 space-y-3">
                {STEPS.map((label, index) => {
                  const tone = toneClasses(stageTone(activeProject, index));
                  return (
                    <div key={label} className={`rounded-2xl border px-4 py-3 ${tone}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{label}</span>
                        <span className="text-xs uppercase tracking-[0.25em]">
                          {index + 1}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                Credits
              </p>
              <p className="mt-3 text-3xl font-semibold text-white">
                {creditBalance ?? "—"}
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Estimated cost for the next video: {productionEstimate} credits
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                Recent Outputs
              </p>
              <h2 className="mt-2 text-xl font-semibold text-white">
                Finished videos and approved scripts
              </h2>
            </div>
            <button
              className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-300"
              type="button"
              onClick={() => setActiveNav("library")}
            >
              Open Library
            </button>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {completedVideos.slice(0, 3).map((project) => (
              <article
                key={project.project_id}
                className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4"
              >
                <p className="text-sm font-semibold text-white">{project.title}</p>
                <p className="mt-1 text-xs text-slate-500">
                  Updated {new Date(project.updated_at).toLocaleString()}
                </p>
                {project.final_video_url ? (
                  <video
                    className="mt-3 w-full rounded-xl border border-slate-800"
                    controls
                    src={project.final_video_url}
                  />
                ) : null}
              </article>
            ))}
            {completedVideos.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                Completed videos will appear here after production finishes.
              </div>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  function renderProjects() {
    return (
      <section className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
              Projects
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white">
              Keep every story in a clear stage
            </h2>
          </div>
          <button
            className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
            type="button"
            onClick={() => {
              setSelectedProjectId(null);
              setSelectedProject(null);
              setCharacters(null);
              setTitleInput("");
              setIdeaInput("");
              setGenreInput("");
              setDurationInput(3);
              setScriptInput("");
              setActiveNav("create");
            }}
          >
            Create New Project
          </button>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.map((project) => (
            <article
              key={project.project_id}
              className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-white">{project.title}</h3>
                  <p className="mt-2 text-sm text-slate-400">
                    {project.idea_prompt || project.topic}
                  </p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs ${statusPill(project.workflow_state)}`}>
                  {workflowStageLabel(project.workflow_state)}
                </span>
              </div>
              <div className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                <p>Last updated: {new Date(project.updated_at).toLocaleString()}</p>
                <p>Duration target: {project.target_duration_minutes || 3} min</p>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                  type="button"
                  onClick={() => {
                    setSelectedProjectId(project.project_id);
                    setActiveNav("create");
                  }}
                >
                  Continue Project
                </button>
                <button
                  className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-300"
                  type="button"
                  onClick={() => setSelectedProjectId(project.project_id)}
                >
                  Select
                </button>
              </div>
            </article>
          ))}
          {projects.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
              No projects yet. Create one from the guided workflow.
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  function renderCreate() {
    return (
      <section className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
              Create
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white">
              Guided story-to-video workflow
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              className="rounded-full border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-200"
              value={selectedProjectId ?? ""}
              onChange={(event) => {
                const next = event.target.value || null;
                setSelectedProjectId(next);
                if (!next) {
                  setSelectedProject(null);
                  setCharacters(null);
                  setTitleInput("");
                  setIdeaInput("");
                  setGenreInput("");
                  setDurationInput(3);
                  setScriptInput("");
                }
              }}
            >
              <option value="">New project</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.55fr]">
          <div className="space-y-6">
            <div className="grid gap-3 lg:grid-cols-4">
              {STEPS.map((label, index) => {
                const tone = toneClasses(stageTone(selectedProject, index));
                return (
                  <button
                    key={label}
                    className={`rounded-2xl border px-4 py-4 text-left transition ${tone}`}
                    type="button"
                    disabled={!stageUnlocked(selectedProject, index)}
                  >
                    <p className="text-[11px] uppercase tracking-[0.25em]">
                      Step {index + 1}
                    </p>
                    <p className="mt-2 text-sm font-semibold">{label}</p>
                  </button>
                );
              })}
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                    Step 1
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Story Request</h3>
                </div>
                <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-400">
                  {selectedProject ? workflowStageLabel(selectedProject.workflow_state) : "New project"}
                </span>
              </div>
              <form className="mt-6 space-y-4" onSubmit={handleGenerateScript}>
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Project Title
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                      placeholder="A brave inventor saves the town"
                      value={titleInput}
                      onChange={(event) => setTitleInput(event.target.value)}
                      required
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Genre
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                      placeholder="Adventure"
                      value={genreInput}
                      onChange={(event) => setGenreInput(event.target.value)}
                    />
                  </label>
                </div>
                <label className="space-y-2">
                  <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Story Idea
                  </span>
                  <textarea
                    className="min-h-[120px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                    placeholder="Describe the idea, tone, and what should happen."
                    value={ideaInput}
                    onChange={(event) => setIdeaInput(event.target.value)}
                  />
                </label>
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Target Duration
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      type="number"
                      min={1}
                      max={120}
                      value={durationInput}
                      onChange={(event) => setDurationInput(Number(event.target.value) || 3)}
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Script Tone
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                      placeholder="cinematic"
                      value={toneInput}
                      onChange={(event) => setToneInput(event.target.value)}
                    />
                  </label>
                </div>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-60"
                  type="submit"
                  disabled={busy === "script"}
                >
                  {busy === "script" ? "Generating Script..." : "Generate Script"}
                </button>
              </form>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                    Step 2
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Review Script</h3>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs ${selectedProject && stageUnlocked(selectedProject, 1) ? "bg-aurora/15 text-aurora" : "bg-slate-800 text-slate-500"}`}>
                  {stageUnlocked(selectedProject, 1) ? "Unlocked" : "Locked"}
                </span>
              </div>
              <textarea
                className="mt-6 min-h-[280px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-4 text-sm leading-7 text-slate-100 outline-none disabled:cursor-not-allowed disabled:opacity-70"
                value={scriptInput}
                onChange={(event) => setScriptInput(event.target.value)}
                disabled={!stageUnlocked(selectedProject, 1)}
              />
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleSaveScript}
                  disabled={!stageUnlocked(selectedProject, 1) || busy === "save-script"}
                >
                  {busy === "save-script" ? "Saving..." : "Edit Script"}
                </button>
                <button
                  className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleRegenerateScript}
                  disabled={!selectedProject || busy === "regenerate-script"}
                >
                  {busy === "regenerate-script" ? "Regenerating..." : "Regenerate Script"}
                </button>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleApproveScript}
                  disabled={!selectedProject || !stageUnlocked(selectedProject, 1) || busy === "approve-script"}
                >
                  {busy === "approve-script" ? "Approving..." : "Approve Script"}
                </button>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                    Step 3
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Choose Characters</h3>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs ${stageUnlocked(selectedProject, 2) ? "bg-aurora/15 text-aurora" : "bg-slate-800 text-slate-500"}`}>
                  {stageUnlocked(selectedProject, 2) ? "Unlocked" : "Approve script first"}
                </span>
              </div>

              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                  Selected Cast
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(characters?.selected ?? []).map((character) => (
                    <span
                      key={character.character_id}
                      className="rounded-full border border-aurora/30 bg-aurora/10 px-3 py-1 text-xs text-aurora"
                    >
                      {character.name}
                    </span>
                  ))}
                  {characters?.selected?.length ? null : (
                    <span className="text-sm text-slate-400">
                      No characters selected yet.
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-6 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Character Name
                      </span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        value={characterName}
                        onChange={(event) => setCharacterName(event.target.value)}
                        disabled={!stageUnlocked(selectedProject, 2)}
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Role Type
                      </span>
                      <select
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        value={characterRole}
                        onChange={(event) => setCharacterRole(event.target.value)}
                        disabled={!stageUnlocked(selectedProject, 2)}
                      >
                        <option value="main">Main</option>
                        <option value="supporting">Supporting</option>
                        <option value="extra">Extra</option>
                        <option value="npc">NPC</option>
                      </select>
                    </label>
                  </div>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Description
                    </span>
                    <textarea
                      className="min-h-[120px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      value={characterDescription}
                      onChange={(event) => setCharacterDescription(event.target.value)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Traits
                      </span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        placeholder="brave, witty, curious"
                        value={characterTraits}
                        onChange={(event) => setCharacterTraits(event.target.value)}
                        disabled={!stageUnlocked(selectedProject, 2)}
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Voice Profile
                      </span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        value={characterVoice}
                        onChange={(event) => setCharacterVoice(event.target.value)}
                        disabled={!stageUnlocked(selectedProject, 2)}
                      />
                    </label>
                  </div>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Reference Image URL
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      placeholder="Optional image URL"
                      value={referenceUrl}
                      onChange={(event) => setReferenceUrl(event.target.value)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Upload Reference
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none file:mr-4 file:rounded-full file:border-0 file:bg-aurora/10 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-aurora"
                      type="file"
                      accept="image/*"
                      onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                  </label>
                  <div className="flex flex-wrap gap-3">
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("manual")}
                      disabled={!selectedProject || !stageUnlocked(selectedProject, 2) || busy === "character-manual"}
                    >
                      {busy === "character-manual" ? "Creating..." : "Add Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("generate")}
                      disabled={!selectedProject || !stageUnlocked(selectedProject, 2) || busy === "character-generate"}
                    >
                      {busy === "character-generate" ? "Generating..." : "Generate Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("upload")}
                      disabled={!selectedProject || !stageUnlocked(selectedProject, 2) || busy === "character-upload"}
                    >
                      {busy === "character-upload" ? "Uploading..." : "Upload Character"}
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  {(characters?.library ?? library?.characters ?? []).map((character) => {
                    const selected = characters?.selected_character_ids.includes(character.character_id);
                    return (
                      <button
                        key={character.character_id}
                        className={`w-full rounded-2xl border p-4 text-left transition ${
                          selected
                            ? "border-aurora/40 bg-aurora/10"
                            : "border-slate-800 bg-slate-900/60"
                        }`}
                        type="button"
                        onClick={() => toggleCharacter(character.character_id)}
                        disabled={!selectedProject || !stageUnlocked(selectedProject, 2)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">{character.name}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                              {character.role_type}
                            </p>
                          </div>
                          <span className="rounded-full bg-slate-950/80 px-3 py-1 text-[11px] text-slate-300">
                            {selected ? "Selected" : "Add"}
                          </span>
                        </div>
                        <p className="mt-3 text-sm text-slate-400">{character.description}</p>
                      </button>
                    );
                  })}
                  {(characters?.library?.length ?? library?.characters?.length ?? 0) === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                      Saved characters will appear here as you create them.
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="mt-6">
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleApproveCharacters}
                  disabled={!selectedProject || !stageUnlocked(selectedProject, 2) || busy === "approve-characters" || !(characters?.selected_character_ids.length)}
                >
                  {busy === "approve-characters" ? "Approving..." : "Approve Characters"}
                </button>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                    Step 4
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-white">Produce Video</h3>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs ${stageUnlocked(selectedProject, 3) ? "bg-aurora/15 text-aurora" : "bg-slate-800 text-slate-500"}`}>
                  {stageUnlocked(selectedProject, 3) ? "Ready when you are" : "Approve characters first"}
                </span>
              </div>
              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Script</p>
                  <p className="mt-2 text-sm text-white">
                    {(selectedProject?.script_approved || "").trim() ? "Approved" : "Pending"}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cast</p>
                  <p className="mt-2 text-sm text-white">
                    {selectedProject?.character_package_approved ? "Approved" : "Pending"}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Estimate</p>
                  <p className="mt-2 text-sm text-white">
                    {productionEstimate} credits
                  </p>
                </div>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleStartProduction}
                  disabled={!selectedProject || !stageUnlocked(selectedProject, 3) || busy === "start-production"}
                >
                  {busy === "start-production" ? "Producing..." : "Start Video Production"}
                </button>
              </div>
              {selectedProject?.final_video_url ? (
                <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-sm font-semibold text-white">Final Video</p>
                  <video
                    className="mt-3 w-full rounded-2xl border border-slate-800"
                    controls
                    src={selectedProject.final_video_url}
                  />
                </div>
              ) : null}
            </div>
          </div>

          <aside className="space-y-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                Project Summary
              </p>
              {selectedProject ? (
                <>
                  <h3 className="mt-3 text-lg font-semibold text-white">
                    {selectedProject.title}
                  </h3>
                  <p className="mt-2 text-sm text-slate-400">
                    {selectedProject.idea_prompt || selectedProject.topic}
                  </p>
                  <div className="mt-5 space-y-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Current step</span>
                      <span className="text-slate-100">{STEPS[selectedStage]}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Stage</span>
                      <span className="text-slate-100">{workflowStageLabel(selectedProject.workflow_state)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Target duration</span>
                      <span className="text-slate-100">
                        {selectedProject.target_duration_minutes || 3} min
                      </span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="mt-3 text-sm text-slate-400">
                  Start by entering a story request. The workflow will guide the rest.
                </p>
              )}
            </div>
            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                Approval Guardrails
              </p>
              <ul className="mt-4 space-y-3 text-sm text-slate-300">
                <li>Characters stay locked until the script is approved.</li>
                <li>Video production stays locked until the character package is approved.</li>
                <li>Editing approved content clears downstream approvals to keep production safe.</li>
              </ul>
            </div>
          </aside>
        </div>
      </section>
    );
  }

  function renderLibrary() {
    const charactersTab = library?.characters ?? [];
    const scriptsTab = approvedScripts;
    const videosTab = completedVideos;
    return (
      <section className="space-y-6">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
            Library
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            Reuse approved assets without touching engine settings
          </h2>
        </div>
        <div className="flex flex-wrap gap-3">
          {(["characters", "scripts", "videos"] as LibraryTab[]).map((tab) => (
            <button
              key={tab}
              className={`rounded-full border px-4 py-2 text-sm ${
                libraryTab === tab
                  ? "border-aurora/40 bg-aurora/10 text-aurora"
                  : "border-slate-700 text-slate-300"
              }`}
              type="button"
              onClick={() => setLibraryTab(tab)}
            >
              {tab[0].toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        {libraryTab === "characters" ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {charactersTab.map((character) => (
              <article
                key={character.character_id}
                className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5"
              >
                <p className="text-lg font-semibold text-white">{character.name}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                  {character.role_type}
                </p>
                <p className="mt-3 text-sm text-slate-400">{character.description}</p>
                {character.canonical_image_url ? (
                  <img
                    className="mt-4 w-full rounded-2xl border border-slate-800"
                    src={character.canonical_image_url}
                    alt={character.name}
                  />
                ) : null}
              </article>
            ))}
            {charactersTab.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
                Saved characters will appear here after you add them in the workflow.
              </div>
            ) : null}
          </div>
        ) : null}
        {libraryTab === "scripts" ? (
          <div className="grid gap-4">
            {scriptsTab.map((project) => (
              <article
                key={project.project_id}
                className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold text-white">{project.title}</p>
                    <p className="mt-2 text-sm text-slate-400">
                      {(project.script_approved || "").slice(0, 220)}
                    </p>
                  </div>
                  <button
                    className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                    type="button"
                    onClick={() => {
                      setSelectedProjectId(project.project_id);
                      setActiveNav("create");
                    }}
                  >
                    Open
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        {libraryTab === "videos" ? (
          <div className="grid gap-4 md:grid-cols-2">
            {videosTab.map((project) => (
              <article
                key={project.project_id}
                className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5"
              >
                <p className="text-lg font-semibold text-white">{project.title}</p>
                {project.final_video_url ? (
                  <video
                    className="mt-4 w-full rounded-2xl border border-slate-800"
                    controls
                    src={project.final_video_url}
                  />
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(244,114,182,0.12),transparent_30%)]" />
      <div className="flex min-h-screen">
        <aside className="hidden w-72 shrink-0 border-r border-slate-900/80 bg-slate-950/85 p-6 lg:block">
          <p className="text-xs uppercase tracking-[0.42em] text-slate-500">
            ProCreator
          </p>
          <h1 className="mt-4 text-3xl font-semibold text-white">
            Guided Studio
          </h1>
          <p className="mt-3 text-sm text-slate-400">
            Create videos in a simple, gated flow.
          </p>
          <nav className="mt-10 space-y-3" aria-label="Primary">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                className={`w-full rounded-3xl border p-4 text-left transition ${
                  activeNav === item.id
                    ? "border-aurora/40 bg-aurora/10 text-white"
                    : "border-slate-800 bg-slate-900/55 text-slate-300"
                }`}
                type="button"
                onClick={() => setActiveNav(item.id)}
              >
                <p className="text-sm font-semibold">{item.label}</p>
                <p className="mt-1 text-xs text-slate-500">{item.detail}</p>
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1">
          <header className="border-b border-slate-900/70 bg-slate-950/60">
            <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-6 py-6">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                  Premium workflow
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  Idea → Script → Characters → Video
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-sm text-slate-300">
                  Credits: {creditBalance ?? "—"}
                </div>
                {activeProject ? (
                  <div className={`rounded-full px-4 py-2 text-sm ${statusPill(activeProject.workflow_state)}`}>
                    {workflowStageLabel(activeProject.workflow_state)}
                  </div>
                ) : null}
              </div>
            </div>
          </header>

          <div className="mx-auto max-w-[1600px] px-6 py-8">
            {error ? (
              <div className="mb-6 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                {error}
              </div>
            ) : null}
            {status ? (
              <div className="mb-6 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                {status}
              </div>
            ) : null}
            {loading ? (
              <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-10 text-sm text-slate-400">
                Loading guided workflow...
              </div>
            ) : null}
            {!loading && activeNav === "overview" ? renderOverview() : null}
            {!loading && activeNav === "projects" ? renderProjects() : null}
            {!loading && activeNav === "create" ? renderCreate() : null}
            {!loading && activeNav === "library" ? renderLibrary() : null}
          </div>
        </main>
      </div>
    </div>
  );
}
