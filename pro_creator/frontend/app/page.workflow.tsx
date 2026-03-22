"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  WorkflowCharacterList,
  WorkflowLibrary,
  WorkflowProject,
  WorkflowProductionStatus,
  WorkflowState,
  approveWorkflowCharacters,
  approveWorkflowScript,
  archiveWorkflowProject,
  createWorkflowCharacter,
  createWorkflowProject,
  duplicateWorkflowProject,
  fetchMyCredits,
  fetchWorkflowCharacters,
  fetchWorkflowLibrary,
  fetchWorkflowProductionSummary,
  fetchWorkflowProductionStatus,
  fetchWorkflowProject,
  fetchWorkflowProjects,
  generateWorkflowCharacter,
  generateWorkflowScript,
  regenerateWorkflowScript,
  retryWorkflowProduction,
  selectWorkflowCharacters,
  startWorkflowProduction,
  updateWorkflowScript,
  uploadWorkflowCharacter,
} from "../lib/api";

type NavItem = "overview" | "projects" | "create" | "library";
type LibraryTab = "characters" | "scripts" | "videos";
type CharacterRoleFilter = "all" | "main" | "supporting" | "extra" | "npc";

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

function currentWorkflowStepLabel(project: WorkflowProject | null): string {
  return STEPS[workflowStageIndex(project)] ?? STEPS[0];
}

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

function mobileNavClasses(active: boolean): string {
  if (active) {
    return "border-aurora/40 bg-aurora/10 text-white";
  }
  return "border-slate-800 bg-slate-900/55 text-slate-300";
}

function guidanceClasses(tone: "info" | "warning" | "success" | "danger"): string {
  switch (tone) {
    case "warning":
      return "border-amber-400/25 bg-amber-400/10 text-amber-50";
    case "success":
      return "border-emerald-400/25 bg-emerald-400/10 text-emerald-50";
    case "danger":
      return "border-red-500/25 bg-red-500/10 text-red-50";
    default:
      return "border-aurora/25 bg-aurora/10 text-cyan-50";
  }
}

function createGuidance(
  project: WorkflowProject | null,
  productionStatus: WorkflowProductionStatus | null,
  productionConfirmed: boolean
): { eyebrow: string; title: string; detail: string; tone: "info" | "warning" | "success" | "danger" } {
  if (!project) {
    return {
      eyebrow: "Start here",
      title: "Enter a story title and generate your script.",
      detail: "Characters and video production stay locked until you approve the script draft.",
      tone: "info",
    };
  }

  switch (project.workflow_state) {
    case "script_generating":
      return {
        eyebrow: "Working",
        title: "Your script is being generated.",
        detail: "Stay on Step 2. As soon as the draft is ready, you can review and approve it.",
        tone: "info",
      };
    case "script_generated":
      return {
        eyebrow: "Next step",
        title: "Review the draft and approve the script.",
        detail: "Character selection is locked until the script is explicitly approved.",
        tone: "warning",
      };
    case "script_approved":
    case "characters_in_progress":
      return {
        eyebrow: "Next step",
        title: "Choose the cast for this project.",
        detail: "Select saved characters, create new ones, or upload references before approving the package.",
        tone: "info",
      };
    case "characters_approved":
    case "production_ready":
      return productionConfirmed
        ? {
            eyebrow: "Ready",
            title: "The project is ready for video production.",
            detail: "Start production when you are ready to spend the estimated credits.",
            tone: "success",
          }
        : {
            eyebrow: "Final approval",
            title: "Confirm the approved script and cast before production.",
            detail: "Check the final approval box in Step 4 to unlock video production.",
            tone: "warning",
          };
    case "production_queued":
      return {
        eyebrow: "Queued",
        title: "Video production is queued.",
        detail: "Your approved script and locked cast package are waiting for render capacity.",
        tone: "info",
      };
    case "production_running":
      return {
        eyebrow: "Rendering",
        title: "Video production is running.",
        detail: "ProCreator is generating scenes, voice, and the final video from the approved package.",
        tone: "info",
      };
    case "production_failed":
      return {
        eyebrow: "Attention",
        title: "Production stopped before completion.",
        detail: productionStatus?.last_error || "Review the error and retry production from Step 4.",
        tone: "danger",
      };
    case "video_completed":
      return {
        eyebrow: "Done",
        title: "Your final video is ready.",
        detail: "You can review it here or reopen the project later from Projects or Library.",
        tone: "success",
      };
    default:
      return {
        eyebrow: "Start here",
        title: "Enter a story title and generate your script.",
        detail: "The workflow will unlock each step after approval.",
        tone: "info",
      };
  }
}

function createWorkflowWarnings(project: WorkflowProject | null): string[] {
  if (!project) {
    return [];
  }

  const warnings: string[] = [];

  if ((project.script_draft || "").trim() && !(project.script_approved || "").trim()) {
    warnings.push("Approve the script to unlock character selection.");
  }

  if ((project.script_approved || "").trim() && !project.character_package_approved) {
    warnings.push("Approve the character package before video production can begin.");
  }

  return warnings;
}

type StepBannerTone = "info" | "warning" | "success" | "danger";

function stepBannerClasses(tone: StepBannerTone): string {
  switch (tone) {
    case "warning":
      return "border-amber-400/20 bg-amber-400/10 text-amber-50";
    case "success":
      return "border-emerald-400/20 bg-emerald-400/10 text-emerald-50";
    case "danger":
      return "border-red-500/20 bg-red-500/10 text-red-50";
    default:
      return "border-cyan-400/20 bg-cyan-400/10 text-cyan-50";
  }
}

function stepOneStatus(project: WorkflowProject | null, busy: string | null): { label: string; detail: string; tone: StepBannerTone } {
  if (busy === "script" || project?.workflow_state === "script_generating") {
    return {
      label: "Generating draft",
      detail: "ProCreator is building the full script from your story request.",
      tone: "info",
    };
  }
  if ((project?.script_approved || "").trim()) {
    return {
      label: "Story locked in",
      detail: "The approved script is saved and the story request is complete.",
      tone: "success",
    };
  }
  if ((project?.script_draft || "").trim()) {
    return {
      label: "Draft ready",
      detail: "Your request has produced a draft. Review it before moving on.",
      tone: "success",
    };
  }
  return {
    label: "Ready for input",
    detail: "Enter a title and a short story idea to create the first script draft.",
    tone: "info",
  };
}

function stepTwoStatus(project: WorkflowProject | null, busy: string | null): { label: string; detail: string; tone: StepBannerTone } {
  if (!stageUnlocked(project, 1)) {
    return {
      label: "Waiting on Step 1",
      detail: "Generate a script first to unlock script review.",
      tone: "warning",
    };
  }
  if (busy === "save-script") {
    return {
      label: "Saving edits",
      detail: "Your latest script changes are being stored.",
      tone: "info",
    };
  }
  if (busy === "approve-script") {
    return {
      label: "Approving script",
      detail: "The script is being locked as the approved production version.",
      tone: "info",
    };
  }
  if (busy === "regenerate-script") {
    return {
      label: "Regenerating draft",
      detail: "A fresh draft is being created and later approvals will reset for safety.",
      tone: "warning",
    };
  }
  if ((project?.script_approved || "").trim()) {
    return {
      label: "Approved",
      detail: "The script is approved and character selection is unlocked.",
      tone: "success",
    };
  }
  return {
    label: "Review required",
    detail: "Read the draft carefully, make any edits, then approve it to continue.",
    tone: "warning",
  };
}

function stepThreeStatus(
  project: WorkflowProject | null,
  characters: WorkflowCharacterList | null,
  busy: string | null
): { label: string; detail: string; tone: StepBannerTone } {
  if (!stageUnlocked(project, 2)) {
    return {
      label: "Waiting on Step 2",
      detail: "Approve the script before choosing or creating characters.",
      tone: "warning",
    };
  }
  if (busy === "approve-characters") {
    return {
      label: "Approving cast",
      detail: "The selected character package is being frozen for production.",
      tone: "info",
    };
  }
  if (busy?.startsWith("character-")) {
    return {
      label: "Updating cast",
      detail: "Character changes are being applied to the project.",
      tone: "info",
    };
  }
  if (project?.character_package_approved) {
    return {
      label: "Cast approved",
      detail: "The approved character package is locked and ready for production.",
      tone: "success",
    };
  }
  if ((characters?.selected_character_ids.length ?? 0) > 0) {
    return {
      label: "Approval pending",
      detail: "Your cast is selected. Approve the character package to unlock production.",
      tone: "warning",
    };
  }
  return {
    label: "Choose the cast",
    detail: "Select saved characters or create new ones for this project.",
    tone: "info",
  };
}

function stepFourStatus(
  project: WorkflowProject | null,
  productionStatus: WorkflowProductionStatus | null,
  productionConfirmed: boolean,
  busy: string | null
): { label: string; detail: string; tone: StepBannerTone } {
  if (!stageUnlocked(project, 3)) {
    return {
      label: "Waiting on Step 3",
      detail: "Approve the character package before video production can begin.",
      tone: "warning",
    };
  }
  if (busy === "start-production") {
    return {
      label: "Queueing production",
      detail: "The approved script and cast are being submitted for rendering.",
      tone: "info",
    };
  }
  if (busy === "retry-production") {
    return {
      label: "Retrying production",
      detail: "The project is being requeued with the same approved package.",
      tone: "info",
    };
  }
  if (project?.workflow_state === "production_failed") {
    return {
      label: "Production failed",
      detail: productionStatus?.last_error || "Review the failure and retry from this step.",
      tone: "danger",
    };
  }
  if (project?.workflow_state === "video_completed") {
    return {
      label: "Video complete",
      detail: "The final video is ready and saved to the project library.",
      tone: "success",
    };
  }
  if (project?.workflow_state === "production_queued" || project?.workflow_state === "production_running") {
    return {
      label: project.workflow_state === "production_running" ? "Rendering in progress" : "Queued for production",
      detail: "ProCreator is processing the approved production package.",
      tone: "info",
    };
  }
  if (!productionConfirmed) {
    return {
      label: "Final approval needed",
      detail: "Confirm the approved script and cast to unlock video production.",
      tone: "warning",
    };
  }
  return {
    label: "Ready to produce",
    detail: "The project has everything needed to start rendering the final video.",
    tone: "success",
  };
}

export default function WorkflowHomePage() {
  const [activeNav, setActiveNav] = useState<NavItem>("create");
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("characters");
  const [projects, setProjects] = useState<WorkflowProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<WorkflowProject | null>(null);
  const [characters, setCharacters] = useState<WorkflowCharacterList | null>(null);
  const [library, setLibrary] = useState<WorkflowLibrary | null>(null);
  const [productionStatus, setProductionStatus] = useState<WorkflowProductionStatus | null>(null);
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
  const [canonicalImageUrl, setCanonicalImageUrl] = useState("");
  const [lockCharacterIdentity, setLockCharacterIdentity] = useState(true);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [productionConfirmed, setProductionConfirmed] = useState(false);
  const [characterSearch, setCharacterSearch] = useState("");
  const [characterRoleFilter, setCharacterRoleFilter] = useState<CharacterRoleFilter>("all");
  const storyRequestRef = useRef<HTMLDivElement | null>(null);
  const scriptReviewRef = useRef<HTMLDivElement | null>(null);
  const charactersRef = useRef<HTMLDivElement | null>(null);
  const productionRef = useRef<HTMLDivElement | null>(null);

  const selectedStage = workflowStageIndex(selectedProject);
  const activeProject = selectedProject ?? projects[0] ?? null;
  const guidance = createGuidance(selectedProject, productionStatus, productionConfirmed);
  const workflowWarnings = createWorkflowWarnings(selectedProject);
  const storyStatus = stepOneStatus(selectedProject, busy);
  const scriptStatus = stepTwoStatus(selectedProject, busy);
  const characterStatus = stepThreeStatus(selectedProject, characters, busy);
  const productionStepStatus = stepFourStatus(selectedProject, productionStatus, productionConfirmed, busy);

  const approvedScripts = useMemo(
    () => (library?.scripts ?? projects.filter((project) => Boolean((project.script_approved || "").trim()))),
    [library, projects]
  );
  const completedVideos = useMemo(
    () => (library?.videos ?? projects.filter((project) => Boolean((project.final_video_url || "").trim()))),
    [library, projects]
  );
  const visibleCharacterLibrary = useMemo(() => {
    const source = characters?.library ?? library?.characters ?? [];
    const query = characterSearch.trim().toLowerCase();
    return source.filter((character) => {
      const matchesRole = characterRoleFilter === "all" || character.role_type === characterRoleFilter;
      if (!matchesRole) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [
        character.name,
        character.description,
        character.role_type,
        ...(character.personality_traits ?? []),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [characterRoleFilter, characterSearch, characters?.library, library?.characters]);

  function scrollToCreateStep(stepIndex: number) {
    const target = [
      storyRequestRef.current,
      scriptReviewRef.current,
      charactersRef.current,
      productionRef.current,
    ][stepIndex];
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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
      nextSelectedId !== undefined
        ? nextSelectedId
        : selectedProjectId ?? workflowProjects[0]?.project_id ?? null;
    if (preferredId) {
      setSelectedProjectId(preferredId);
    } else {
      setSelectedProjectId(null);
      setSelectedProject(null);
      setCharacters(null);
    }
  }

  async function refreshProject(projectId: string) {
    const [project, nextCharacters, summary, nextProductionStatus] = await Promise.all([
      fetchWorkflowProject(projectId),
      fetchWorkflowCharacters(projectId).catch(() => null),
      fetchWorkflowProductionSummary(projectId).catch(() => null),
      fetchWorkflowProductionStatus(projectId).catch(() => null),
    ]);
    setSelectedProject(project);
    setCharacters(nextCharacters);
    setProductionStatus(nextProductionStatus);
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
        await refreshProjects();
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

  useEffect(() => {
    setProductionConfirmed(false);
  }, [selectedProject?.project_id, selectedProject?.script_approved_at, selectedProject?.character_package_approved_at]);

  useEffect(() => {
    if (!selectedProjectId || !selectedProject) {
      return;
    }
    if (
      selectedProject.workflow_state !== "production_queued" &&
      selectedProject.workflow_state !== "production_running"
    ) {
      return;
    }
    const interval = window.setInterval(async () => {
      try {
        const nextStatus = await fetchWorkflowProductionStatus(selectedProjectId);
        setProductionStatus(nextStatus);
        if (nextStatus.workflow_state !== selectedProject.workflow_state) {
          await refreshProject(selectedProjectId);
          await refreshProjects(selectedProjectId);
        }
      } catch {
        // Keep the page stable during temporary polling failures.
      }
    }, 4000);
    return () => window.clearInterval(interval);
  }, [selectedProjectId, selectedProject?.workflow_state]);

  async function afterProjectMutation(projectId: string, message: string) {
    await refreshProjects(projectId);
    await refreshProject(projectId);
    setStatus(message);
    setError(null);
  }

  async function handleArchiveProject(projectId: string) {
    setBusy(`archive-${projectId}`);
    setError(null);
    setStatus(null);
    try {
      const archivedProject = await archiveWorkflowProject(projectId);
      const remainingProjects = projects.filter((project) => project.project_id !== projectId);
      const fallbackProjectId =
        selectedProjectId === projectId ? remainingProjects[0]?.project_id ?? null : selectedProjectId;
      await refreshProjects(fallbackProjectId);
      if (fallbackProjectId) {
        await refreshProject(fallbackProjectId);
      }
      setStatus(`${archivedProject.title} was archived.`);
      setError(null);
      if (!fallbackProjectId) {
        setSelectedProject(null);
        setCharacters(null);
        setProductionStatus(null);
        setScriptInput("");
        setTitleInput("");
        setIdeaInput("");
        setGenreInput("");
        setDurationInput(3);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive project");
    } finally {
      setBusy(null);
    }
  }

  async function handleDuplicateProject(projectId: string) {
    setBusy(`duplicate-${projectId}`);
    setError(null);
    setStatus(null);
    try {
      const duplicate = await duplicateWorkflowProject(projectId);
      setActiveNav("create");
      await afterProjectMutation(duplicate.project_id, `${duplicate.title} is ready as a new project copy.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to duplicate project");
    } finally {
      setBusy(null);
    }
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
      await afterProjectMutation(
        updated.project_id,
        selectedProject?.script_approved || selectedProject?.character_package_approved
          ? "A new script draft is ready. Script and character approvals were cleared for safety."
          : "Script draft is ready for review."
      );
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
      await afterProjectMutation(
        updated.project_id,
        "A new script draft has been generated. Script and character approvals were cleared."
      );
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
      setStatus(
        selectedProject.character_package_approved
          ? "Character approval was cleared because the cast changed."
          : "Character selection updated."
      );
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
      const cleanName = characterName.trim();
      const cleanDescription = characterDescription.trim();
      if (!cleanName) {
        throw new Error("Add a character name before continuing.");
      }
      if (!cleanDescription) {
        throw new Error("Add a short character description before continuing.");
      }
      const traits = characterTraits
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const referenceUrls = referenceUrl
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const cleanCanonicalImageUrl = canonicalImageUrl.trim();
      let nextCharacters: WorkflowCharacterList;
      if (mode === "generate") {
        nextCharacters = await generateWorkflowCharacter(selectedProject.project_id, {
          name: cleanName,
          role_type: characterRole,
          description: cleanDescription,
          personality_traits: traits,
          voice_profile: characterVoice,
          style: "cinematic",
          lock_identity: lockCharacterIdentity,
          select_after_create: true,
        });
      } else if (mode === "upload") {
        if (!uploadFile) {
          throw new Error("Choose a reference image before uploading");
        }
        nextCharacters = await uploadWorkflowCharacter(selectedProject.project_id, {
          file: uploadFile,
          name: cleanName,
          role_type: characterRole,
          description: cleanDescription,
          voice_profile: characterVoice,
          lock_identity: lockCharacterIdentity,
          select_after_create: true,
        });
      } else {
        nextCharacters = await createWorkflowCharacter(selectedProject.project_id, {
          name: cleanName,
          role_type: characterRole,
          description: cleanDescription,
          reference_image_url: referenceUrls[0],
          reference_image_urls: referenceUrls,
          canonical_image_url: cleanCanonicalImageUrl || undefined,
          personality_traits: traits,
          voice_profile: characterVoice,
          lock_identity: lockCharacterIdentity,
          select_after_create: true,
        });
      }
      setCharacters(nextCharacters);
      setCharacterName("");
      setCharacterDescription("");
      setCharacterTraits("");
      setReferenceUrl("");
      setCanonicalImageUrl("");
      setLockCharacterIdentity(true);
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
    if (!productionConfirmed) {
      setError("Please confirm the approved script and cast before starting production.");
      setStatus(null);
      return;
    }
    setBusy("start-production");
    setError(null);
    setStatus(null);
    try {
      const response = await startWorkflowProduction(selectedProject.project_id);
      setProductionStatus(response.status);
      setProductionConfirmed(false);
      await afterProjectMutation(
        response.project.project_id,
        "Video production has been queued."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start production");
    } finally {
      setBusy(null);
    }
  }

  async function handleRetryProduction() {
    if (!selectedProject) return;
    setBusy("retry-production");
    setError(null);
    setStatus(null);
    try {
      const nextStatus = await retryWorkflowProduction(selectedProject.project_id);
      setProductionStatus(nextStatus);
      await afterProjectMutation(selectedProject.project_id, "Video production has been queued again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry production");
    } finally {
      setBusy(null);
    }
  }

  function productionDetailLabel() {
    if (!productionStatus?.queue_status) {
      return selectedProject?.workflow_state ? workflowStageLabel(selectedProject.workflow_state) : "Waiting";
    }
    switch (productionStatus.queue_status) {
      case "queued":
        return "Queued for production";
      case "running":
      case "processing":
        return "Production running";
      case "complete":
        return "Video completed";
      case "failed":
        return "Production failed";
      default:
        return productionStatus.queue_status;
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
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                    type="button"
                    onClick={() => setActiveNav("create")}
                  >
                    Start First Project
                  </button>
                  <button
                    className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-300"
                    type="button"
                    onClick={() => setActiveNav("library")}
                  >
                    Browse Library
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div ref={charactersRef} className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
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
                <p>Current step: {currentWorkflowStepLabel(project)}</p>
                <p>Selected cast: {project.selected_character_ids.length}</p>
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
                <button
                  className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-300"
                  type="button"
                  disabled={busy === `duplicate-${project.project_id}`}
                  onClick={() => void handleDuplicateProject(project.project_id)}
                >
                  {busy === `duplicate-${project.project_id}` ? "Duplicating..." : "Duplicate"}
                </button>
                <button
                  className="rounded-full border border-red-500/30 px-4 py-2 text-sm text-red-200"
                  type="button"
                  disabled={busy === `archive-${project.project_id}`}
                  onClick={() => void handleArchiveProject(project.project_id)}
                >
                  {busy === `archive-${project.project_id}` ? "Archiving..." : "Archive"}
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

        <div className={`rounded-3xl border p-5 sm:p-6 ${guidanceClasses(guidance.tone)}`}>
          <p className="text-xs uppercase tracking-[0.3em] opacity-80">{guidance.eyebrow}</p>
          <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-lg font-semibold text-white">{guidance.title}</h3>
              <p className="mt-2 max-w-3xl text-sm text-slate-200/90">{guidance.detail}</p>
            </div>
            {selectedProject ? (
              <div className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-100">
                Current step: {STEPS[selectedStage]}
              </div>
            ) : null}
          </div>
          {workflowWarnings.length > 0 ? (
            <div className="mt-4 space-y-2">
              {workflowWarnings.map((warning) => (
                <div
                  key={warning}
                  className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-100"
                >
                  {warning}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.55fr]">
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {STEPS.map((label, index) => {
                const tone = toneClasses(stageTone(selectedProject, index));
                return (
                  <button
                    key={label}
                    className={`rounded-2xl border px-4 py-4 text-left transition ${tone}`}
                    type="button"
                    onClick={() => scrollToCreateStep(index)}
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

            <div ref={storyRequestRef} className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
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
              {!selectedProject ? (
                <div className="mt-5 rounded-2xl border border-dashed border-aurora/25 bg-aurora/5 p-4">
                  <p className="text-sm text-slate-200">
                    Start with a title or a short idea. ProCreator will generate the full script first, then unlock characters after approval.
                  </p>
                </div>
              ) : null}
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(storyStatus.tone)}`}>
                <p className="font-semibold text-white">{storyStatus.label}</p>
                <p className="mt-1 text-slate-200/90">{storyStatus.detail}</p>
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
                <div className="flex flex-wrap gap-3">
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-60"
                    type="submit"
                    disabled={busy === "script"}
                  >
                    {busy === "script" ? "Generating Script..." : "Generate Script"}
                  </button>
                  <button
                    className="rounded-full border border-slate-700 px-5 py-3 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={() => scrollToCreateStep(1)}
                    disabled={!stageUnlocked(selectedProject, 1)}
                  >
                    Go to Script Review
                  </button>
                </div>
              </form>
            </div>

            <div ref={scriptReviewRef} className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
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
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(scriptStatus.tone)}`}>
                <p className="font-semibold text-white">{scriptStatus.label}</p>
                <p className="mt-1 text-slate-200/90">{scriptStatus.detail}</p>
              </div>
              <textarea
                className="mt-6 min-h-[280px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-4 text-sm leading-7 text-slate-100 outline-none disabled:cursor-not-allowed disabled:opacity-70"
                value={scriptInput}
                onChange={(event) => setScriptInput(event.target.value)}
                disabled={!stageUnlocked(selectedProject, 1)}
              />
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                  type="button"
                  onClick={() => scrollToCreateStep(0)}
                >
                  Back to Story Request
                </button>
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
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(characterStatus.tone)}`}>
                <p className="font-semibold text-white">{characterStatus.label}</p>
                <p className="mt-1 text-slate-200/90">{characterStatus.detail}</p>
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
                      Reference Images
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      placeholder="Optional image URLs, separated by commas"
                      value={referenceUrl}
                      onChange={(event) => setReferenceUrl(event.target.value)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Canonical Image URL
                    </span>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      placeholder="Optional approved hero image URL"
                      value={canonicalImageUrl}
                      onChange={(event) => setCanonicalImageUrl(event.target.value)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                  </label>
                  <label className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
                    <input
                      className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-950 text-aurora"
                      type="checkbox"
                      checked={lockCharacterIdentity}
                      onChange={(event) => setLockCharacterIdentity(event.target.checked)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                    <span>
                      <span className="block text-sm font-semibold text-white">Lock character identity</span>
                      <span className="mt-1 block text-xs text-slate-400">
                        Keep the same approved face, prompt base, and reference bundle through production.
                      </span>
                    </span>
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
                  <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      placeholder="Search saved characters"
                      value={characterSearch}
                      onChange={(event) => setCharacterSearch(event.target.value)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    />
                    <select
                      className="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                      value={characterRoleFilter}
                      onChange={(event) => setCharacterRoleFilter(event.target.value as CharacterRoleFilter)}
                      disabled={!stageUnlocked(selectedProject, 2)}
                    >
                      <option value="all">All roles</option>
                      <option value="main">Main</option>
                      <option value="supporting">Supporting</option>
                      <option value="extra">Extra</option>
                      <option value="npc">NPC</option>
                    </select>
                  </div>
                  {visibleCharacterLibrary.map((character) => {
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
                        {character.reference_image_urls.length > 0 ? (
                          <p className="mt-3 text-xs text-slate-500">
                            {character.reference_image_urls.length} reference image
                            {character.reference_image_urls.length === 1 ? "" : "s"}
                          </p>
                        ) : null}
                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                          <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                            {character.lock_identity ? "Identity locked" : "Identity flexible"}
                          </span>
                          {character.canonical_image_url ? (
                            <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                              Canonical image
                            </span>
                          ) : null}
                        </div>
                      </button>
                    );
                  })}
                  {visibleCharacterLibrary.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                      No characters match the current search or filter yet.
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-slate-700 px-5 py-3 text-sm text-slate-200"
                  type="button"
                  onClick={() => scrollToCreateStep(1)}
                  disabled={!stageUnlocked(selectedProject, 2)}
                >
                  Back to Script Review
                </button>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleApproveCharacters}
                  disabled={!selectedProject || !stageUnlocked(selectedProject, 2) || busy === "approve-characters" || !(characters?.selected_character_ids.length)}
                >
                  {busy === "approve-characters" ? "Approving..." : "Approve Characters"}
                </button>
                <button
                  className="rounded-full border border-slate-700 px-5 py-3 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={() => scrollToCreateStep(3)}
                  disabled={!stageUnlocked(selectedProject, 3)}
                >
                  Go to Produce Video
                </button>
              </div>
            </div>

            <div ref={productionRef} className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
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
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(productionStepStatus.tone)}`}>
                <p className="font-semibold text-white">{productionStepStatus.label}</p>
                <p className="mt-1 text-slate-200/90">{productionStepStatus.detail}</p>
              </div>
              <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Job Status</p>
                  <p className="mt-2 text-sm text-white">
                    {productionDetailLabel()}
                  </p>
                  {productionStatus?.queue_status ? (
                    <p className="mt-1 text-xs text-slate-500">
                      Attempts {productionStatus.queue_attempts} / {productionStatus.queue_max_attempts || 3}
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <label className="flex items-start gap-3">
                  <input
                    className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-950 text-aurora"
                    type="checkbox"
                    checked={productionConfirmed}
                    onChange={(event) => setProductionConfirmed(event.target.checked)}
                    disabled={!selectedProject || !stageUnlocked(selectedProject, 3)}
                  />
                  <span className="text-sm text-slate-200">
                    I approve this script and cast for full video production.
                  </span>
                </label>
                <p className="mt-2 text-xs text-slate-500">
                  This is the final approval step before rendering begins.
                </p>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  className="rounded-full border border-slate-700 px-5 py-3 text-sm text-slate-200"
                  type="button"
                  onClick={() => scrollToCreateStep(2)}
                  disabled={!stageUnlocked(selectedProject, 2)}
                >
                  Back to Characters
                </button>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleStartProduction}
                  disabled={
                    !selectedProject ||
                    !stageUnlocked(selectedProject, 3) ||
                    !productionConfirmed ||
                    busy === "start-production" ||
                    selectedProject.workflow_state === "production_queued" ||
                    selectedProject.workflow_state === "production_running"
                  }
                >
                  {busy === "start-production" ? "Queueing..." : "Start Video Production"}
                </button>
                {selectedProject?.workflow_state === "production_failed" || productionStatus?.can_retry ? (
                  <button
                    className="rounded-full border border-red-400/30 bg-red-500/10 px-5 py-3 text-sm font-semibold text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={handleRetryProduction}
                    disabled={busy === "retry-production"}
                  >
                    {busy === "retry-production" ? "Retrying..." : "Retry Production"}
                  </button>
                ) : null}
              </div>
              {productionStatus?.last_error ? (
                <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                  {productionStatus.last_error}
                </div>
              ) : null}
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
                <div className="mt-3 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-4">
                  <p className="text-sm text-slate-300">
                    Start by entering a story request. The workflow will guide the rest.
                  </p>
                  <ul className="mt-4 space-y-2 text-sm text-slate-400">
                    <li>1. Enter the story title and idea.</li>
                    <li>2. Review and approve the generated script.</li>
                    <li>3. Choose characters before production unlocks.</li>
                  </ul>
                </div>
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
          <>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <input
                className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                placeholder="Search characters"
                value={characterSearch}
                onChange={(event) => setCharacterSearch(event.target.value)}
              />
              <select
                className="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                value={characterRoleFilter}
                onChange={(event) => setCharacterRoleFilter(event.target.value as CharacterRoleFilter)}
              >
                <option value="all">All roles</option>
                <option value="main">Main</option>
                <option value="supporting">Supporting</option>
                <option value="extra">Extra</option>
                <option value="npc">NPC</option>
              </select>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleCharacterLibrary.map((character) => (
              <article
                key={character.character_id}
                className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5"
              >
                <p className="text-lg font-semibold text-white">{character.name}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                  {character.role_type}
                </p>
                <p className="mt-3 text-sm text-slate-400">{character.description}</p>
                {character.reference_image_urls.length > 0 ? (
                  <p className="mt-3 text-xs text-slate-500">
                    {character.reference_image_urls.length} reference image
                    {character.reference_image_urls.length === 1 ? "" : "s"}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                  <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                    {character.lock_identity ? "Identity locked" : "Identity flexible"}
                  </span>
                  {character.canonical_image_url ? (
                    <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                      Canonical image
                    </span>
                  ) : null}
                </div>
                {character.canonical_image_url ? (
                  <img
                    className="mt-4 w-full rounded-2xl border border-slate-800"
                    src={character.canonical_image_url}
                    alt={character.name}
                  />
                ) : null}
              </article>
            ))}
            {visibleCharacterLibrary.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
                No saved characters match the current search or role filter.
              </div>
            ) : null}
            </div>
          </>
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
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                    type="button"
                    onClick={() => {
                      setSelectedProjectId(project.project_id);
                      setActiveNav("create");
                    }}
                  >
                    Continue In Create
                  </button>
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    disabled={busy === `duplicate-${project.project_id}`}
                    onClick={() => void handleDuplicateProject(project.project_id)}
                  >
                    {busy === `duplicate-${project.project_id}` ? "Duplicating..." : "Duplicate Into New Project"}
                  </button>
                </div>
              </article>
            ))}
            {scriptsTab.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
                Approved scripts will appear here after you finish script review.
              </div>
            ) : null}
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
                  <>
                    <video
                      className="mt-4 w-full rounded-2xl border border-slate-800"
                      controls
                      src={project.final_video_url}
                    />
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                        type="button"
                        onClick={() => {
                          setSelectedProjectId(project.project_id);
                          setActiveNav("create");
                        }}
                      >
                        Open Project
                      </button>
                      <a
                        className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                        href={project.final_video_url}
                        download
                      >
                        Download Video
                      </a>
                      <button
                        className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        disabled={busy === `duplicate-${project.project_id}`}
                        onClick={() => void handleDuplicateProject(project.project_id)}
                      >
                        {busy === `duplicate-${project.project_id}` ? "Duplicating..." : "Reuse As New Project"}
                      </button>
                    </div>
                  </>
                ) : null}
              </article>
            ))}
            {videosTab.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
                Completed videos will appear here after production finishes.
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(244,114,182,0.12),transparent_30%)]" />
      <div className="min-h-screen lg:flex">
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
            <div className="mx-auto flex max-w-[1600px] flex-col items-start gap-4 px-4 py-5 sm:px-6 sm:py-6 lg:flex-row lg:items-center lg:justify-between">
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
            <div className="border-t border-slate-900/60 px-4 py-3 sm:px-6 lg:hidden">
              <nav className="grid grid-cols-2 gap-3" aria-label="Primary mobile">
                {NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    className={`rounded-2xl border px-4 py-3 text-left transition ${mobileNavClasses(activeNav === item.id)}`}
                    type="button"
                    onClick={() => setActiveNav(item.id)}
                  >
                    <p className="text-sm font-semibold">{item.label}</p>
                    <p className="mt-1 text-xs text-slate-500">{item.detail}</p>
                  </button>
                ))}
              </nav>
            </div>
          </header>

          <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 sm:py-8">
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
