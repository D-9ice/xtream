"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ProjectCard from "../components/ProjectCard";
import type {
  AuthGateStatus,
  CreditPlan,
  ExportStatusEntry,
  ImageResponse,
  OrchestrationQueueItem,
  OrchestrationScheduleItem,
  Project,
  ScriptResponse,
  ThumbnailResponse,
  VideoResponse,
  VoiceResponse,
} from "../lib/api";
import {
  changePassword,
  clearScript,
  createStripeCheckoutSession,
  createOrchestrationSchedule,
  createProject,
  deleteAllProjects,
  deleteVoiceProfile,
  editByText,
  enqueueOrchestrationBatch,
  enqueueOrchestrationJob,
  exportBatch,
  exportPreset,
  fetchArtifact,
  fetchCreditPlans,
  fetchExportStatus,
  fetchAuthGateStatus,
  fetchOrchestrationQueue,
  fetchOrchestrationRunnerStatus,
  fetchOrchestrationSchedules,
  fetchMyCredits,
  fetchProjects,
  fetchVoiceProfiles,
  generateImage,
  generateScript,
  generateThumbnail,
  generateVoice,
  importScript,
  importVideoUrl,
  processOrchestrationQueue,
  purgeStaleProjects,
  renderVideo,
  retryOrchestrationJob,
  runOrchestrationSchedules,
  setPrimaryThumbnail,
  startOrchestrationRunner,
  stopOrchestrationRunner,
  triggerFeature,
  updateAuthGateStatus,
  updateLiveScript,
  uploadVoiceProfile,
} from "../lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";
const PROJECTS_BASE =
  process.env.NEXT_PUBLIC_PROJECTS_BASE ?? `${API_BASE}/projects`;

const panels = [
  { id: "overview", label: "Overview", icon: "✨" },
  { id: "projects", label: "Projects", icon: "📁" },
  { id: "engines", label: "Engines", icon: "⚡" },
  { id: "automation", label: "Automation", icon: "🤖" },
  { id: "orchestration", label: "Orchestration", icon: "🧭" },
  { id: "logs", label: "Logs", icon: "🧾" },
];

const captionTemplates = [
  {
    id: "bold",
    label: "Bold highlight",
    style: "bold",
    size: 28,
    textColor: "text-white",
    bgColor: "bg-aurora/80",
  },
  {
    id: "minimal",
    label: "Minimal",
    style: "minimal",
    size: 20,
    textColor: "text-slate-100",
    bgColor: "bg-black/40",
  },
  {
    id: "karaoke",
    label: "Karaoke",
    style: "karaoke",
    size: 24,
    textColor: "text-amber-100",
    bgColor: "bg-amber-500/20",
  },
];

type LogEntry = {
  timestamp: string;
  message: string;
  status: "ok" | "error";
  engine: string;
};

export default function HomePage() {
  const experimentalEnabled =
    process.env.NEXT_PUBLIC_EXPERIMENTAL_FEATURES === "true";
  const [activePanel, setActivePanel] = useState("overview");
  const [signedIn, setSignedIn] = useState(false);
  const [hasMounted, setHasMounted] = useState(false);
  const [showAccountPanel, setShowAccountPanel] = useState(false);
  const [accountTab, setAccountTab] = useState<"plans" | "access">("plans");
  const [authGateStatus, setAuthGateStatus] = useState<AuthGateStatus | null>(null);
  const [authGateLoading, setAuthGateLoading] = useState(true);
  const [authGateUpdating, setAuthGateUpdating] = useState(false);
  const [authGateError, setAuthGateError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordStatus, setPasswordStatus] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [logFilter, setLogFilter] = useState<"all" | "ok" | "error">("all");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [projectsRefreshToken, setProjectsRefreshToken] = useState(0);
  const projectsFetchSeq = useRef(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createLoading, setCreateLoading] = useState(false);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineMessage, setPipelineMessage] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [stalePurgeDays, setStalePurgeDays] = useState(30);

  const [enginesTab, setEnginesTab] = useState("script");
  const [automationTab, setAutomationTab] = useState("captions");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [featureStatus, setFeatureStatus] = useState<string | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<string | null>(null);
  const [actionLogs, setActionLogs] = useState<LogEntry[]>([]);

  const [scriptTone, setScriptTone] = useState("neutral");
  const [scriptDuration, setScriptDuration] = useState(3);
  const [scriptImportText, setScriptImportText] = useState("");
  const [scriptResult, setScriptResult] = useState<ScriptResponse | null>(null);
  const [scriptEditText, setScriptEditText] = useState("");
  const [isEditingScript, setIsEditingScript] = useState(false);
  const [lastDeletedScript, setLastDeletedScript] = useState<string | null>(null);
  const [scriptRefreshToken, setScriptRefreshToken] = useState(0);
  const [liveScriptEnabled, setLiveScriptEnabled] = useState(false);
  const [liveScriptStatus, setLiveScriptStatus] = useState<string | null>(null);
  const [liveScriptSaving, setLiveScriptSaving] = useState(false);
  const [useLiveScriptForVoice, setUseLiveScriptForVoice] = useState(false);
  const liveScriptTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [voiceText, setVoiceText] = useState(
    "Narrate the project in a calm, professional tone."
  );
  const [voiceProvider, setVoiceProvider] = useState("xtts");
  const [voiceProfiles, setVoiceProfiles] = useState<string[]>(["default"]);
  const [selectedVoiceProfile, setSelectedVoiceProfile] = useState("default");
  const [voiceResult, setVoiceResult] = useState<VoiceResponse | null>(null);
  const [voiceProfileName, setVoiceProfileName] = useState("");
  const [voiceProfileFile, setVoiceProfileFile] = useState<File | null>(null);
  const [voiceProfilePath, setVoiceProfilePath] = useState<string | null>(null);
  const [voiceCloneStatus, setVoiceCloneStatus] = useState<string | null>(null);

  const [imagePrompt, setImagePrompt] = useState("");
  const [imageStyle, setImageStyle] = useState("cinematic");
  const [imageResult, setImageResult] = useState<ImageResponse | null>(null);

  const [videoResult, setVideoResult] = useState<VideoResponse | null>(null);
  const [videoImportUrl, setVideoImportUrl] = useState("");
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [thumbnailResult, setThumbnailResult] = useState<ThumbnailResponse | null>(null);
  const [thumbnailMode, setThumbnailMode] = useState<"classic" | "ai">("classic");
  const [thumbnailTitle, setThumbnailTitle] = useState("");
  const [thumbnailSubtitle, setThumbnailSubtitle] = useState("");
  const [thumbnailAiPrompt, setThumbnailAiPrompt] = useState("");
  const [thumbnailStyle, setThumbnailStyle] = useState("cinematic");
  const [thumbnailVariantCount, setThumbnailVariantCount] = useState(3);
  const [thumbnailSource, setThumbnailSource] = useState<"auto" | "video" | "image">(
    "auto"
  );
  const [thumbnailTimestamp, setThumbnailTimestamp] = useState(1);

  const [editRanges, setEditRanges] = useState("");

  const [captionStyle, setCaptionStyle] = useState("bold");
  const [captionSize, setCaptionSize] = useState(28);
  const [captionTextColor, setCaptionTextColor] = useState("text-white");
  const [captionBgColor, setCaptionBgColor] = useState("bg-aurora/80");
  const [selectedCaptionTemplate, setSelectedCaptionTemplate] = useState("bold");

  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportQueue, setExportQueue] = useState<ExportStatusEntry[]>([]);

  const [queueItems, setQueueItems] = useState<OrchestrationQueueItem[]>([]);
  const [scheduleItems, setScheduleItems] = useState<OrchestrationScheduleItem[]>(
    []
  );
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueStatus, setQueueStatus] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueKind, setQueueKind] = useState("full");
  const [queueTopic, setQueueTopic] = useState("");
  const [queueDuration, setQueueDuration] = useState(3);
  const [queueTone, setQueueTone] = useState("neutral");
  const [queuePreset, setQueuePreset] = useState("youtube");
  const [batchCount, setBatchCount] = useState(3);
  const [runnerRunning, setRunnerRunning] = useState(false);
  const [scheduleCadence, setScheduleCadence] = useState(7);
  const [creditsRemaining, setCreditsRemaining] = useState<number | null>(null);
  const [creditsUsed, setCreditsUsed] = useState<number | null>(null);
  const [creditsTotal, setCreditsTotal] = useState<number | null>(null);
  const [creditPlans, setCreditPlans] = useState<CreditPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [purchaseLoadingPlan, setPurchaseLoadingPlan] = useState<string | null>(null);
  const [purchaseStatus, setPurchaseStatus] = useState<string | null>(null);

  const captionSizeClass = `text-[${captionSize}px]`;
  const logStats = useMemo(() => {
    const total = actionLogs.length;
    const errors = actionLogs.filter((entry) => entry.status === "error").length;
    return { total, errors, ok: total - errors };
  }, [actionLogs]);
  const filteredLogs = useMemo(() => {
    if (logFilter === "all") {
      return actionLogs;
    }
    return actionLogs.filter((entry) => entry.status === logFilter);
  }, [actionLogs, logFilter]);

  const bumpScriptRefresh = () =>
    setScriptRefreshToken((prev) => (prev + 1) % 1000);

  const resolveMediaUrl = (path?: string | null) => {
    if (!path) {
      return null;
    }
    if (path.startsWith("http")) {
      return path;
    }
    if (path.startsWith("/")) {
      return `${API_BASE}${path}`;
    }
    return `${API_BASE}/${path}`;
  };

  const videoPreviewFallback = useMemo(() => {
    if (!selectedProjectId) {
      return null;
    }
    return `${PROJECTS_BASE}/${selectedProjectId}/video/final.mp4`;
  }, [selectedProjectId]);

  const accessAllowed = signedIn || authGateStatus?.enabled === false;
  const authGateLocked = authGateStatus?.source === "env";

  const refreshProjects = useCallback(() => {
    // Forces a refetch without coupling project loading to selection changes.
    setProjectsRefreshToken((prev) => prev + 1);
  }, []);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const updateAuthState = () => {
      setSignedIn(Boolean(window.localStorage.getItem("pc_token")));
    };
    updateAuthState();
    const handleStorage = (event: StorageEvent) => {
      if (event.key === "pc_token") {
        updateAuthState();
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  useEffect(() => {
    let active = true;
    setAuthGateLoading(true);
    setAuthGateError(null);
    fetchAuthGateStatus()
      .then((status) => {
        if (active) {
          setAuthGateStatus(status);
        }
      })
      .catch((err) => {
        if (active) {
          setAuthGateStatus(null);
          setAuthGateError(err instanceof Error ? err.message : "Failed to load password gate");
        }
      })
      .finally(() => {
        if (active) {
          setAuthGateLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (authGateStatus?.enabled === false && !signedIn) {
      setAccountTab("access");
    }
  }, [authGateStatus?.enabled, signedIn]);

  const refreshCredits = useCallback(async () => {
    try {
      const credits = await fetchMyCredits();
      setCreditsRemaining(credits.credits_balance);
      setCreditsUsed(credits.credits_used_total);
      setCreditsTotal(credits.credits_balance + credits.credits_used_total);
    } catch {
      setCreditsRemaining(null);
      setCreditsUsed(null);
      setCreditsTotal(null);
    }
  }, []);

  useEffect(() => {
    if (!accessAllowed) {
      setCreditsRemaining(null);
      setCreditsUsed(null);
      setCreditsTotal(null);
      return;
    }
    refreshCredits();
  }, [accessAllowed, refreshCredits]);

  useEffect(() => {
    if (!accessAllowed || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const checkoutState = params.get("checkout");
    if (!checkoutState) {
      return;
    }
    if (checkoutState === "success") {
      setPurchaseStatus("Payment completed. Credits update after webhook confirmation.");
      void refreshCredits();
    } else if (checkoutState === "cancel") {
      setPurchaseStatus("Checkout canceled.");
    }
    params.delete("checkout");
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [accessAllowed, refreshCredits]);

  useEffect(() => {
    if (!accessAllowed) {
      setCreditPlans([]);
      return;
    }
    let active = true;
    setPlansLoading(true);
    fetchCreditPlans()
      .then((response) => {
        if (!active) {
          return;
        }
        setCreditPlans(response.plans ?? []);
      })
      .catch(() => {
        if (active) {
          setCreditPlans([]);
        }
      })
      .finally(() => {
        if (active) {
          setPlansLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [accessAllowed]);

  useEffect(() => {
    if (!signedIn || typeof window === "undefined") {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      const isAccel = event.metaKey || event.ctrlKey;
      if (!isAccel || !event.shiftKey) {
        return;
      }
      if (event.key.toLowerCase() !== "a") {
        return;
      }
      event.preventDefault();
      window.location.href = "/admin";
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [signedIn]);

  const handleSignOut = () => {
    if (typeof window === "undefined") {
      return;
    }
    const confirmed = window.confirm("Sign out of Pro Creator?");
    if (!confirmed) {
      return;
    }
    window.localStorage.removeItem("pc_token");
    setSignedIn(false);
    setShowAccountPanel(false);
    if (window.opener) {
      window.close();
      return;
    }
    if (authGateStatus?.enabled === false) {
      window.location.href = "/";
      return;
    }
    window.location.href = "/login";
  };

  const handlePurchasePlan = async (planId: string) => {
    setPurchaseStatus(null);
    setPurchaseLoadingPlan(planId);
    try {
      const checkout = await createStripeCheckoutSession({ plan_id: planId });
      if (typeof window !== "undefined") {
        window.location.href = checkout.checkout_url;
      }
    } catch (err) {
      setPurchaseStatus(
        err instanceof Error ? err.message : "Purchase failed"
      );
    } finally {
      setPurchaseLoadingPlan(null);
    }
  };

  const handlePasswordChange = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordError(null);
    setPasswordStatus(null);
    const requireCurrentPassword = authGateStatus?.enabled !== false;
    if (requireCurrentPassword && !currentPassword) {
      setPasswordError("Enter your current password.");
      return;
    }
    if (!newPassword) {
      setPasswordError("Enter your new password.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }
    setPasswordLoading(true);
    try {
      await changePassword({
        current_password: currentPassword || "",
        new_password: newPassword,
      });
      setPasswordStatus("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePasswordGateToggle = async (nextEnabled: boolean) => {
    if (typeof window === "undefined") {
      return;
    }
    if (authGateLocked) {
      return;
    }
    const message = nextEnabled
      ? "Enable the password gate? You'll need to sign in after this. Set your password first if you haven't already."
      : "Disable the password gate? Anyone with access to this machine/network will be able to use the app without signing in.";
    const confirmed = window.confirm(message);
    if (!confirmed) {
      return;
    }

    setAuthGateError(null);
    setAuthGateUpdating(true);
    try {
      const updated = await updateAuthGateStatus(nextEnabled);
      setAuthGateStatus(updated);

      // If enabling, force a clean sign-in flow.
      if (nextEnabled) {
        window.localStorage.removeItem("pc_token");
        setSignedIn(false);
        setShowAccountPanel(false);
        window.location.href = "/login";
        return;
      }

      // If disabling, return to the app in "open" mode.
      window.location.href = "/";
    } catch (err) {
      setAuthGateError(err instanceof Error ? err.message : "Failed to update password gate");
    } finally {
      setAuthGateUpdating(false);
    }
  };

  useEffect(() => {
    if (!accessAllowed) {
      setProjects([]);
      setSelectedProjectId("");
      return;
    }

    let active = true;
    const seq = (projectsFetchSeq.current += 1);
    const loadProjects = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchProjects();
        if (!active || seq !== projectsFetchSeq.current) {
          return;
        }
        setProjects(data);
        setSelectedProjectId((prev) => {
          if (prev && data.some((p) => p.project_id === prev)) {
            return prev;
          }
          return data[0]?.project_id ?? "";
        });
      } catch (err) {
        if (!active || seq !== projectsFetchSeq.current) {
          // stale request
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load projects");
      } finally {
        if (active && seq === projectsFetchSeq.current) {
          setLoading(false);
        }
      }
    };

    loadProjects();
    return () => {
      active = false;
    };
  }, [accessAllowed, projectsRefreshToken]);

  useEffect(() => {
    let active = true;
    if (!selectedProjectId) {
      setVoiceProfiles(["default"]);
      setSelectedVoiceProfile("default");
      return;
    }
    const loadProfiles = async () => {
      try {
        const profiles = await fetchVoiceProfiles(selectedProjectId);
        if (active) {
          const nextProfiles = profiles.length ? profiles : ["default"];
          setVoiceProfiles(nextProfiles);
          setSelectedVoiceProfile(nextProfiles[0]);
        }
      } catch {
        if (active) {
          setVoiceProfiles(["default"]);
          setSelectedVoiceProfile("default");
        }
      }
    };
    loadProfiles();
    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    let active = true;
    const loadOrchestration = async () => {
      try {
        const [queue, schedules, runner] = await Promise.all([
          fetchOrchestrationQueue(),
          fetchOrchestrationSchedules(),
          fetchOrchestrationRunnerStatus(),
        ]);
        if (active) {
          setQueueItems(queue.items ?? []);
          setScheduleItems(schedules.items ?? []);
          setRunnerRunning(runner.running);
        }
      } catch {
        if (active) {
          setQueueItems([]);
        }
      }
    };
    loadOrchestration();
    return () => {
      active = false;
    };
  }, []);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setCreateLoading(true);
    try {
      const project = await createProject({ title, topic });
      setProjects((prev) => [project, ...prev]);
      setSelectedProjectId(project.project_id);
      setTitle("");
      setTopic("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleGenerateScript = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    const generatorPrompt = scriptImportText.trim() || queueTopic.trim() || topic.trim();
    if (!generatorPrompt) {
      setActionError(
        "Add a title/topic prompt in the script input box, then generate."
      );
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await generateScript({
        project_id: selectedProjectId,
        topic: generatorPrompt,
        duration_minutes: scriptDuration,
        tone: scriptTone,
      });
      setScriptResult(response);
      setScriptEditText(response.full_script);
      setVoiceText(response.full_script);
      await refreshCredits();
      bumpScriptRefresh();
      setActionLogs((prev) => [
        {
          timestamp: new Date().toLocaleTimeString(),
          message: "Script generated",
          status: "ok",
          engine: "script",
        },
        ...prev,
      ]);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Script generation failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleImportScript = async () => {
    if (!selectedProjectId || !scriptImportText.trim()) {
      setActionError("Paste a script to import.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await importScript({
        project_id: selectedProjectId,
        script: scriptImportText,
      });
      setScriptResult(response);
      setScriptEditText(response.full_script);
      setVoiceText(response.full_script);
      bumpScriptRefresh();
      setScriptImportText("");
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Script import failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveScriptEdit = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await importScript({
        project_id: selectedProjectId,
        script: scriptEditText,
      });
      setScriptResult(response);
      setVoiceText(response.full_script);
      setIsEditingScript(false);
      bumpScriptRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Script update failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleClearScript = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    const confirmed = window.confirm(
      "Delete the script and scene metadata? This cannot be undone unless you restore it immediately."
    );
    if (!confirmed) {
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      setLastDeletedScript(scriptResult?.full_script ?? null);
      const response = await clearScript({ project_id: selectedProjectId });
      setScriptResult(response);
      setScriptEditText("");
      setIsEditingScript(false);
      bumpScriptRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Script delete failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleUndoScriptDelete = async () => {
    if (!selectedProjectId || !lastDeletedScript) {
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await importScript({
        project_id: selectedProjectId,
        script: lastDeletedScript,
      });
      setScriptResult(response);
      setScriptEditText(response.full_script);
      setVoiceText(response.full_script);
      setLastDeletedScript(null);
      bumpScriptRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Script restore failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateVoice = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const resolvedVoiceText = useLiveScriptForVoice
        ? scriptEditText.trim() || voiceText
        : voiceText;
      const response = await generateVoice({
        project_id: selectedProjectId,
        text: resolvedVoiceText,
        voice_profile: selectedVoiceProfile,
        tts_provider: voiceProvider,
      });
      setVoiceResult(response);
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Voice generation failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleUploadVoiceProfile = async () => {
    if (!selectedProjectId || !voiceProfileFile || !voiceProfileName.trim()) {
      setActionError("Provide a name and sample to clone.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await uploadVoiceProfile({
        project_id: selectedProjectId,
        profile_name: voiceProfileName,
        file: voiceProfileFile,
        tts_provider: voiceProvider,
      });
      setVoiceProfilePath(response.profile_path);
      setVoiceCloneStatus("Voice clone complete.");
      const profiles = await fetchVoiceProfiles(selectedProjectId);
      setVoiceProfiles(profiles.length ? profiles : ["default"]);
      setVoiceProfileFile(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Voice clone failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleLiveScriptLipsync = async () => {
    if (!selectedProjectId) {
      setLiveScriptStatus("Select a project first.");
      return;
    }
    setLiveScriptSaving(true);
    try {
      await updateLiveScript({
        project_id: selectedProjectId,
        script: scriptEditText,
        update_scenes: false,
      });
      const response = await triggerFeature({
        path: "/video/lipsync",
        project_id: selectedProjectId,
      });
      setLiveScriptStatus(
        `Live script synced. ${response.detail ?? response.status}`
      );
    } catch (err) {
      setLiveScriptStatus(
        err instanceof Error ? err.message : "Live sync/lipsync failed"
      );
    } finally {
      setLiveScriptSaving(false);
    }
  };

  useEffect(() => {
    if (!liveScriptEnabled || !selectedProjectId) {
      return;
    }
    if (liveScriptTimeout.current) {
      clearTimeout(liveScriptTimeout.current);
    }
    setLiveScriptSaving(true);
    liveScriptTimeout.current = setTimeout(async () => {
      try {
        await updateLiveScript({
          project_id: selectedProjectId,
          script: scriptEditText,
          update_scenes: false,
        });
        setLiveScriptStatus("Live script synced.");
      } catch (err) {
        setLiveScriptStatus(
          err instanceof Error ? err.message : "Live script sync failed"
        );
      } finally {
        setLiveScriptSaving(false);
      }
    }, 600);
    return () => {
      if (liveScriptTimeout.current) {
        clearTimeout(liveScriptTimeout.current);
      }
    };
  }, [liveScriptEnabled, scriptEditText, selectedProjectId]);

  const handleDeleteVoiceProfile = async (profile: string) => {
    if (!selectedProjectId) {
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      await deleteVoiceProfile({
        project_id: selectedProjectId,
        profile_name: profile,
      });
      const profiles = await fetchVoiceProfiles(selectedProjectId);
      const nextProfiles = profiles.length ? profiles : ["default"];
      setVoiceProfiles(nextProfiles);
      setSelectedVoiceProfile(nextProfiles[0]);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Profile delete failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateImage = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await generateImage({
        project_id: selectedProjectId,
        prompt: imagePrompt,
        style: imageStyle,
      });
      setImageResult(response);
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Image generation failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRenderVideo = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await renderVideo({ project_id: selectedProjectId });
      setVideoResult(response);
      setVideoPreviewUrl(resolveMediaUrl(response.video_path));
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Video render failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleImportVideoUrl = async () => {
    if (!selectedProjectId || !videoImportUrl.trim()) {
      setActionError("Provide a video URL to import.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await importVideoUrl({
        project_id: selectedProjectId,
        url: videoImportUrl,
      });
      setVideoResult(response);
      setVideoPreviewUrl(resolveMediaUrl(response.video_path) ?? videoImportUrl);
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Video import failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateThumbnail = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await generateThumbnail({
        project_id: selectedProjectId,
        mode: thumbnailMode,
        title: thumbnailTitle || undefined,
        subtitle: thumbnailSubtitle || undefined,
        ai_prompt: thumbnailMode === "ai" ? thumbnailAiPrompt || undefined : undefined,
        style: thumbnailStyle || "cinematic",
        variant_count: thumbnailMode === "ai" ? thumbnailVariantCount : 1,
        source: thumbnailSource,
        timestamp_seconds: thumbnailTimestamp,
        format: "png",
        width: 1280,
        height: 720,
      });
      setThumbnailResult(response);
      await refreshCredits();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Thumbnail generation failed"
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleSetPrimaryThumbnail = async (thumbnailKey: string) => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await setPrimaryThumbnail({
        project_id: selectedProjectId,
        thumbnail_key: thumbnailKey,
      });
      setThumbnailResult(response);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Set primary thumbnail failed"
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerFeature = async (path: string, label: string) => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await triggerFeature({
        path,
        project_id: selectedProjectId,
      });
      setFeatureStatus(`${label}: ${response.detail ?? response.status}`);
      if (path.includes("captions")) {
        const artifact = await fetchArtifact({
          project_id: selectedProjectId,
          artifact: "captions",
        });
        setArtifactPreview(JSON.stringify(artifact, null, 2));
      }
      if (path.includes("lipsync")) {
        const artifact = await fetchArtifact({
          project_id: selectedProjectId,
          artifact: "lipsync",
        });
        setArtifactPreview(JSON.stringify(artifact, null, 2));
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `${label} failed`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditByText = async () => {
    if (!selectedProjectId || !editRanges.trim()) {
      setActionError("Add transcript ranges first.");
      return;
    }
    const ranges = editRanges
      .split(",")
      .map((segment) => segment.trim())
      .filter(Boolean)
      .map((segment) => segment.split("-").map(Number))
      .filter((pair) => pair.length === 2 && pair.every((value) => !Number.isNaN(value)));
    if (ranges.length === 0) {
      setActionError("Provide ranges like 0-5, 12-16.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await editByText({
        project_id: selectedProjectId,
        remove_ranges: ranges,
      });
      setFeatureStatus(`Edit applied. Segments left: ${response.segments_remaining}.`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Edit failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleExportPreset = async (preset: string) => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      const response = await exportPreset({ project_id: selectedProjectId, preset });
      setExportStatus(`Export ready: ${response.export_path}`);
      const status = await fetchExportStatus({ project_id: selectedProjectId });
      setExportQueue(status.exports ?? []);
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleExportBatch = async () => {
    if (!selectedProjectId) {
      setActionError("Select a project first.");
      return;
    }
    setActionError(null);
    setActionLoading(true);
    try {
      await exportBatch({
        project_id: selectedProjectId,
        presets: ["youtube", "tiktok", "instagram"],
      });
      const status = await fetchExportStatus({ project_id: selectedProjectId });
      setExportQueue(status.exports ?? []);
      setExportStatus("Batch export triggered.");
      await refreshCredits();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Batch export failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAllProjects = async () => {
    setPipelineError(null);
    setPipelineMessage(null);
    setPipelineLoading(true);
    try {
      const response = await deleteAllProjects();
      // Invalidate any in-flight project fetches so stale responses can't repopulate the UI.
      projectsFetchSeq.current += 1;
      setProjects([]);
      setSelectedProjectId("");
      setPipelineMessage(`Deleted ${response.deleted_count} projects.`);
      refreshProjects();
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setPipelineLoading(false);
    }
  };

  const handlePurgeStaleProjects = async () => {
    setPipelineError(null);
    setPipelineMessage(null);
    setPipelineLoading(true);
    try {
      const response = await purgeStaleProjects({ min_age_days: stalePurgeDays });
      setPipelineMessage(`Purged ${response.deleted_count} projects.`);
      refreshProjects();
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "Purge failed");
    } finally {
      setPipelineLoading(false);
    }
  };

  const handleEnqueueJob = async () => {
    if (!selectedProjectId) {
      setQueueError("Select a project first.");
      return;
    }
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = await enqueueOrchestrationJob({
        project_id: selectedProjectId,
        kind: queueKind,
        topic: queueTopic || undefined,
        duration_minutes: queueDuration,
        tone: queueTone,
        export_preset: queuePreset,
      });
      setQueueItems((prev) => [response, ...prev]);
      setQueueStatus("Job queued.");
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Queue failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleEnqueueBatch = async () => {
    if (!selectedProjectId) {
      setQueueError("Select a project first.");
      return;
    }
    setQueueLoading(true);
    setQueueError(null);
    try {
      const items = Array.from({ length: batchCount }, () => ({
        project_id: selectedProjectId,
        kind: queueKind,
        topic: queueTopic || undefined,
        duration_minutes: queueDuration,
        tone: queueTone,
        export_preset: queuePreset,
      }));
      const response = await enqueueOrchestrationBatch({ items });
      setQueueItems((prev) => [...response.items, ...prev]);
      setQueueStatus(`Batch queued (${response.items.length}).`);
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Batch queue failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleProcessQueue = async () => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = await processOrchestrationQueue({ limit: 1 });
      setQueueStatus(`Processed ${response.processed} job(s).`);
      const queue = await fetchOrchestrationQueue();
      setQueueItems(queue.items ?? []);
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Process failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleRetryJob = async (jobId: number) => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = await retryOrchestrationJob(jobId);
      setQueueItems((prev) =>
        prev.map((item) => (item.id === jobId ? response : item))
      );
      setQueueStatus("Retry triggered.");
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleRunnerToggle = async () => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = runnerRunning
        ? await stopOrchestrationRunner()
        : await startOrchestrationRunner({ interval_seconds: 30 });
      setRunnerRunning(response.running);
      setQueueStatus(response.running ? "Runner started." : "Runner stopped.");
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Runner failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleCreateSchedule = async () => {
    if (!selectedProjectId) {
      setQueueError("Select a project first.");
      return;
    }
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = await createOrchestrationSchedule({
        project_id: selectedProjectId,
        cadence_days: scheduleCadence,
      });
      setScheduleItems((prev) => [response, ...prev]);
      setQueueStatus("Schedule created.");
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Schedule failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleRunSchedules = async () => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const response = await runOrchestrationSchedules();
      setScheduleItems(response.items ?? []);
      setQueueStatus("Schedules run.");
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Run schedules failed");
    } finally {
      setQueueLoading(false);
    }
  };

  const handleExportLogs = () => {
    if (typeof window === "undefined") {
      return;
    }
    const payload = JSON.stringify(actionLogs, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pro-creator-logs.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleCopyLogs = async () => {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(JSON.stringify(actionLogs, null, 2));
  };

  const applyCaptionTemplate = (templateId: string) => {
    const template = captionTemplates.find((item) => item.id === templateId);
    if (!template) {
      return;
    }
    setSelectedCaptionTemplate(template.id);
    setCaptionStyle(template.style);
    setCaptionSize(template.size);
    setCaptionTextColor(template.textColor);
    setCaptionBgColor(template.bgColor);
  };

  const renderEnginesSection = () => (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Engine actions</h2>
          <p className="mt-1 text-sm text-slate-400">
            Trigger the AI engines for a selected project.
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        {[
          { key: "script", label: "Script" },
          { key: "voice", label: "Voice" },
          { key: "image", label: "Image" },
          { key: "video", label: "Video" },
          ...(experimentalEnabled
            ? [
                { key: "media", label: "Media" },
                { key: "lab", label: "Lab" },
              ]
            : []),
        ].map((tab) => (
          <button
            key={tab.key}
            className={`rounded-full border px-3 py-1 ${
              enginesTab === tab.key
                ? "border-aurora/40 bg-aurora/10 text-aurora"
                : "border-slate-700 text-slate-300"
            }`}
            type="button"
            onClick={() => setEnginesTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {enginesTab === "script" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Script input</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleImportScript}
                disabled={actionLoading}
              >
                Import
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Paste a full script to import, or write a title + prompt and click Generate.
            </p>
            <textarea
              className="min-h-[120px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={scriptImportText}
              onChange={(event) => setScriptImportText(event.target.value)}
              placeholder={"Title: Building a Business\nPrompt: Write a 3-minute script for small business owners..."}
            />
          </div>
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Script generator</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleGenerateScript}
                disabled={actionLoading}
              >
                Generate
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label
                  className="text-xs uppercase tracking-wide text-slate-400"
                  htmlFor="script-tone"
                >
                  Tone
                </label>
                <input
                  id="script-tone"
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                  value={scriptTone}
                  onChange={(event) => setScriptTone(event.target.value)}
                  placeholder="neutral"
                />
              </div>
              <div>
                <label
                  className="text-xs uppercase tracking-wide text-slate-400"
                  htmlFor="script-duration"
                >
                  Duration (min)
                </label>
                <input
                  id="script-duration"
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                  type="number"
                  min={0.25}
                  step={0.05}
                  value={scriptDuration}
                  onChange={(event) => setScriptDuration(Number(event.target.value))}
                />
                <p className="mt-1 text-[11px] text-slate-500">
                  Common ad lengths: 0.25 = 15s, 0.5 = 30s, 1 = 60s.
                </p>
              </div>
            </div>
            {scriptResult ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-300">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-200">Script ready</p>
                  <div className="flex items-center gap-2">
                    <button
                      className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-200"
                      type="button"
                      onClick={() => setIsEditingScript((prev) => !prev)}
                    >
                      {isEditingScript ? "Cancel" : "Edit"}
                    </button>
                    <button
                      className="rounded-full border border-red-500/40 px-2 py-1 text-[10px] text-red-200"
                      type="button"
                      onClick={handleClearScript}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {isEditingScript ? (
                  <textarea
                    className="mt-3 min-h-[120px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
                    aria-label="Edit script"
                    value={scriptEditText}
                    onChange={(event) => setScriptEditText(event.target.value)}
                  />
                ) : (
                  <div className="mt-2 max-h-72 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                    <p className="whitespace-pre-line text-xs leading-relaxed text-slate-200">
                      {scriptResult.full_script}
                    </p>
                  </div>
                )}
                {isEditingScript ? (
                  <button
                    className="mt-3 rounded-lg bg-aurora px-3 py-2 text-[10px] font-semibold text-slate-900"
                    type="button"
                    onClick={handleSaveScriptEdit}
                    disabled={actionLoading}
                  >
                    Save script
                  </button>
                ) : null}
                {!isEditingScript && lastDeletedScript ? (
                  <button
                    className="mt-3 rounded-lg border border-aurora/60 px-3 py-2 text-[10px] font-semibold text-aurora"
                    type="button"
                    onClick={handleUndoScriptDelete}
                    disabled={actionLoading}
                  >
                    Undo delete
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {enginesTab === "voice" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Voice</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleGenerateVoice}
                disabled={actionLoading}
              >
                Generate
              </button>
            </div>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="voice-provider"
            >
              TTS provider
            </label>
            <select
              id="voice-provider"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={voiceProvider}
              onChange={(event) => setVoiceProvider(event.target.value)}
            >
              <option value="xtts">XTTS (self-hosted)</option>
              <option value="elevenlabs">ElevenLabs</option>
            </select>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="voice-profile"
            >
              Voice profile
            </label>
            <select
              id="voice-profile"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={selectedVoiceProfile}
              onChange={(event) => setSelectedVoiceProfile(event.target.value)}
            >
              {voiceProfiles.map((profile) => (
                <option key={profile} value={profile}>
                  {profile}
                </option>
              ))}
            </select>
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-100">Live script (Descript-style)</p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Edit the script while TTS is running. Changes sync in the background.
                  </p>
                </div>
                <label className="flex items-center gap-2 text-[11px] text-slate-300">
                  <input
                    type="checkbox"
                    checked={liveScriptEnabled}
                    aria-label="Enable live script sync"
                    onChange={(event) => setLiveScriptEnabled(event.target.checked)}
                  />
                  Live sync
                </label>
                <button
                  className="rounded-md border border-slate-700 px-2 py-1 text-[11px]"
                  type="button"
                  onClick={handleLiveScriptLipsync}
                  disabled={liveScriptSaving}
                >
                  Sync + refresh lipsync
                </button>
              </div>
              <label className="mt-2 flex items-center gap-2 text-[11px] text-slate-300">
                <input
                  type="checkbox"
                  checked={useLiveScriptForVoice}
                  aria-label="Use live script for voice generation"
                  onChange={(event) => setUseLiveScriptForVoice(event.target.checked)}
                />
                Use live script for voice generation
              </label>
              {liveScriptEnabled ? (
                <textarea
                  className="mt-3 min-h-[120px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
                  aria-label="Live script editor"
                  value={scriptEditText}
                  onChange={(event) => setScriptEditText(event.target.value)}
                />
              ) : null}
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                <span>
                  {liveScriptSaving
                    ? "Syncing..."
                    : liveScriptStatus ?? "Live sync idle"}
                </span>
                <span>
                  {useLiveScriptForVoice ? "Live script active" : "Prompt active"}
                </span>
              </div>
            </div>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="voice-prompt"
            >
              Voice prompt
            </label>
            <textarea
              id="voice-prompt"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={voiceText}
              onChange={(event) => setVoiceText(event.target.value)}
              placeholder="Narrate the project in a calm, professional tone."
            />
            {voiceResult ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-300">
                <p className="font-semibold text-slate-200">Voice ready</p>
                <audio
                  className="mt-2 w-full"
                  controls
                  preload="none"
                  src={resolveMediaUrl(voiceResult.audio_path) ?? undefined}
                />
                <a
                  className="mt-2 inline-flex text-[11px] text-aurora hover:underline"
                  href={resolveMediaUrl(voiceResult.audio_path) ?? voiceResult.audio_path}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open audio file
                </a>
              </div>
            ) : null}
          </div>
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div>
              <h4 className="text-lg font-semibold">Clone voice</h4>
              <p className="mt-1 text-xs text-slate-400">
                Upload a short WAV sample and name the clone.
              </p>
            </div>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="voice-profile-name"
            >
              Clone name
            </label>
            <input
              id="voice-profile-name"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={voiceProfileName}
              onChange={(event) => setVoiceProfileName(event.target.value)}
            />
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="voice-profile-file"
            >
              Clone sample
            </label>
            <input
              id="voice-profile-file"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              type="file"
              accept="audio/wav"
              onChange={(event) =>
                setVoiceProfileFile(event.target.files?.[0] ?? null)
              }
            />
            <button
              className="rounded-lg border border-aurora/40 px-3 py-2 text-xs text-aurora"
              type="button"
              onClick={handleUploadVoiceProfile}
              disabled={actionLoading || !voiceProfileFile}
            >
              Clone voice
            </button>
            {voiceProfilePath ? (
              <p className="text-xs text-slate-400">
                Clone saved: {voiceProfilePath}
              </p>
            ) : null}
            {voiceCloneStatus ? (
              <p className="text-xs text-emerald-300">{voiceCloneStatus}</p>
            ) : null}
            {voiceProfiles.length > 0 ? (
              <div className="space-y-2 text-xs">
                {voiceProfiles.map((profile) => (
                  <div
                    key={profile}
                    className="flex items-center justify-between rounded-md border border-slate-800 px-2 py-2"
                  >
                    <span className="text-slate-300">{profile}</span>
                    <button
                      className="rounded-full border border-red-500/40 px-2 py-1 text-[10px] text-red-200"
                      type="button"
                      onClick={() => handleDeleteVoiceProfile(profile)}
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {enginesTab === "image" ? (
        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Image</h3>
            <button
              className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
              type="button"
              onClick={handleGenerateImage}
              disabled={actionLoading}
            >
              Generate
            </button>
          </div>
          <label
            className="text-xs uppercase tracking-wide text-slate-400"
            htmlFor="image-prompt"
          >
            Image prompt
          </label>
          <input
            id="image-prompt"
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={imagePrompt}
            onChange={(event) => setImagePrompt(event.target.value)}
            placeholder="Cinematic studio lighting with bold neon accents"
          />
          <label
            className="mt-3 text-xs uppercase tracking-wide text-slate-400"
            htmlFor="image-style"
          >
            Style
          </label>
          <input
            id="image-style"
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={imageStyle}
            onChange={(event) => setImageStyle(event.target.value)}
          />
          {imageResult ? (
            <p className="mt-2 text-xs text-slate-400">
              Image ready: {imageResult.image_path}
            </p>
          ) : null}
        </div>
      ) : null}

      {enginesTab === "video" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Video</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleRenderVideo}
                disabled={actionLoading}
              >
                Render
              </button>
            </div>
            <p className="text-sm text-slate-400">
              Render a full mp4 and review it below or in the project preview
              screen.
            </p>
            {videoResult ? (
              <p className="mt-2 text-xs text-slate-400">
                Video ready: {videoResult.video_path}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <button
                className="rounded-lg border border-aurora/40 px-3 py-2 text-aurora"
                type="button"
                onClick={handleImportVideoUrl}
                disabled={actionLoading}
              >
                Import video URL
              </button>
              {selectedProjectId ? (
                <a
                  className="rounded-lg border border-slate-700 px-3 py-2 text-slate-200"
                  href={`/projects/${selectedProjectId}`}
                >
                  Open preview screen
                </a>
              ) : null}
            </div>
            <input
              className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={videoImportUrl}
              onChange={(event) => setVideoImportUrl(event.target.value)}
              placeholder="https://..."
            />
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <h4 className="text-lg font-semibold">Video output</h4>
            <p className="mt-1 text-xs text-slate-400">
              Preview the latest render for this project.
            </p>
            {videoPreviewUrl || videoPreviewFallback ? (
              <video
                className="mt-3 w-full rounded-xl border border-slate-800"
                controls
                src={videoPreviewUrl ?? videoPreviewFallback ?? undefined}
              />
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                Render or import a video to see the preview.
              </p>
            )}
            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <h5 className="text-sm font-semibold">Thumbnail generator</h5>
                <button
                  className="rounded-lg border border-aurora/40 px-3 py-1.5 text-xs text-aurora"
                  type="button"
                  onClick={handleGenerateThumbnail}
                  disabled={actionLoading}
                >
                  Generate thumbnail
                </button>
              </div>
              <div className="mt-3 grid gap-2">
                <select
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                  value={thumbnailMode}
                  onChange={(event) =>
                    setThumbnailMode(event.target.value as "classic" | "ai")
                  }
                >
                  <option value="classic">Classic thumbnail (from project media)</option>
                  <option value="ai">AI thumbnail (OpenAI quality mode)</option>
                </select>
                <input
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                  value={thumbnailTitle}
                  onChange={(event) => setThumbnailTitle(event.target.value)}
                  placeholder="Thumbnail title"
                />
                <input
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                  value={thumbnailSubtitle}
                  onChange={(event) => setThumbnailSubtitle(event.target.value)}
                  placeholder="Thumbnail subtitle (optional)"
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  {thumbnailMode === "classic" ? (
                    <select
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                      value={thumbnailSource}
                      onChange={(event) =>
                        setThumbnailSource(
                          event.target.value as "auto" | "video" | "image"
                        )
                      }
                    >
                      <option value="auto">Auto source (video then image)</option>
                      <option value="video">Video frame</option>
                      <option value="image">Scene image</option>
                    </select>
                  ) : (
                    <input
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                      value={thumbnailStyle}
                      onChange={(event) => setThumbnailStyle(event.target.value)}
                      placeholder="Style (cinematic, bold, dramatic, etc.)"
                    />
                  )}
                  <input
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                    type="number"
                    min={0}
                    step={0.25}
                    value={thumbnailTimestamp}
                    onChange={(event) =>
                      setThumbnailTimestamp(Number(event.target.value))
                    }
                    placeholder="Frame second"
                  />
                </div>
                {thumbnailMode === "ai" ? (
                  <>
                    <input
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                      type="number"
                      min={1}
                      max={4}
                      value={thumbnailVariantCount}
                      onChange={(event) =>
                        setThumbnailVariantCount(
                          Math.max(1, Math.min(4, Number(event.target.value) || 1))
                        )
                      }
                      placeholder="A/B variant count (1-4)"
                    />
                    <textarea
                      className="min-h-[74px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
                      value={thumbnailAiPrompt}
                      onChange={(event) => setThumbnailAiPrompt(event.target.value)}
                      placeholder="AI creative direction (subject, emotion, framing, color palette, visual motif)"
                    />
                  </>
                ) : null}
              </div>
              {thumbnailResult ? (
                <div className="mt-3">
                  <p className="text-[11px] text-slate-400">
                    Mode: {thumbnailResult.mode_used} • Source: {thumbnailResult.source_used} • {thumbnailResult.width}x
                    {thumbnailResult.height}
                  </p>
                  <img
                    className="mt-2 w-full rounded-lg border border-slate-800"
                    src={resolveMediaUrl(thumbnailResult.thumbnail_path) ?? undefined}
                    alt="Generated thumbnail"
                  />
                  <a
                    className="mt-2 inline-flex text-[11px] text-aurora hover:underline"
                    href={
                      resolveMediaUrl(thumbnailResult.thumbnail_path) ??
                      thumbnailResult.thumbnail_path
                    }
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open thumbnail file
                  </a>
                  {thumbnailResult.variants && thumbnailResult.variants.length > 1 ? (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {thumbnailResult.variants.map((variant) => (
                        <div
                          key={variant.variant_id}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 hover:border-aurora/50"
                        >
                          <p className="text-[11px] text-slate-300">
                            Variant {variant.variant_id}
                          </p>
                          <img
                            className="mt-1 w-full rounded border border-slate-800"
                            src={
                              resolveMediaUrl(variant.thumbnail_path) ?? undefined
                            }
                            alt={`Thumbnail variant ${variant.variant_id}`}
                          />
                          <div className="mt-2 flex items-center justify-between gap-2">
                            <a
                              className="text-[11px] text-aurora hover:underline"
                              href={
                                resolveMediaUrl(variant.thumbnail_path) ??
                                variant.thumbnail_path
                              }
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open
                            </a>
                            <button
                              className="rounded border border-aurora/40 px-2 py-1 text-[10px] text-aurora"
                              type="button"
                              onClick={() =>
                                handleSetPrimaryThumbnail(variant.thumbnail_key)
                              }
                              disabled={actionLoading}
                            >
                              Set as primary
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {enginesTab === "media" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Import video URL</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleImportVideoUrl}
                disabled={actionLoading}
              >
                Import
              </button>
            </div>
            <input
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={videoImportUrl}
              onChange={(event) => setVideoImportUrl(event.target.value)}
              placeholder="https://..."
            />
          </div>
          <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Import script</h3>
              <button
                className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
                type="button"
                onClick={handleImportScript}
                disabled={actionLoading}
              >
                Import
              </button>
            </div>
            <textarea
              className="min-h-[120px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={scriptImportText}
              onChange={(event) => setScriptImportText(event.target.value)}
              placeholder="Paste a prepared script here"
            />
          </div>
        </div>
      ) : null}

      {enginesTab === "lab" ? (
        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="text-lg font-semibold">Edit-by-text</h3>
          <p className="mt-1 text-xs text-slate-400">
            Remove transcript ranges (seconds). Example: 0-5, 12-16
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="edit-ranges">
              Transcript ranges to remove
            </label>
            <input
              id="edit-ranges"
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
              placeholder="0-5, 12-16"
              value={editRanges}
              onChange={(event) => setEditRanges(event.target.value)}
            />
            <button
              className="rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900"
              type="button"
              onClick={handleEditByText}
            >
              Apply cut
            </button>
          </div>
        </div>
      ) : null}

      {actionError ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {actionError}
        </p>
      ) : null}
      {featureStatus ? (
        <p className="mt-2 text-xs text-slate-400">{featureStatus}</p>
      ) : null}
      {artifactPreview ? (
        <pre className="mt-3 max-h-40 overflow-auto rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-200">
          {artifactPreview}
        </pre>
      ) : null}
    </section>
  );

  const renderAutomationSection = () => (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Automation studio</h2>
          <p className="mt-1 text-sm text-slate-400">
            Compact automation surfaces for captions, editing, and exports.
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        {[
          { key: "captions", label: "Captions" },
          { key: "editor", label: "Editor" },
          ...(experimentalEnabled ? [{ key: "lab", label: "AI Lab" }] : []),
          { key: "exports", label: "Exports" },
        ].map((tab) => (
          <button
            key={tab.key}
            className={`rounded-full border px-3 py-1 ${
              automationTab === tab.key
                ? "border-aurora/40 bg-aurora/10 text-aurora"
                : "border-slate-700 text-slate-300"
            }`}
            type="button"
            onClick={() => setAutomationTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Queue</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {queueItems.length} jobs
          </p>
          <p className="text-xs text-slate-400">Last status: {queueStatus ?? "Idle"}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Schedules</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {scheduleItems.length} active
          </p>
          <p className="text-xs text-slate-400">Cadence: {scheduleCadence}d default</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Runner</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {runnerRunning ? "Running" : "Stopped"}
          </p>
          <p className="text-xs text-slate-400">Auto-processing orchestration</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <button
          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
          type="button"
          onClick={handleProcessQueue}
          disabled={queueLoading}
        >
          Process next job
        </button>
        <button
          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
          type="button"
          onClick={handleRunSchedules}
          disabled={queueLoading}
        >
          Run schedules now
        </button>
        <button
          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
          type="button"
          onClick={handleRunnerToggle}
          disabled={queueLoading}
        >
          {runnerRunning ? "Stop" : "Start"} runner
        </button>
      </div>

      {automationTab === "captions" ? (
        <div className="mt-4 grid gap-3 md:grid-cols-[1.2fr_1fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">
              Caption templates
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {captionTemplates.map((template) => (
                <button
                  key={template.id}
                  className={`rounded-lg border px-3 py-2 text-xs ${
                    selectedCaptionTemplate === template.id
                      ? "border-aurora text-aurora"
                      : "border-slate-700 text-slate-200"
                  }`}
                  type="button"
                  onClick={() => applyCaptionTemplate(template.id)}
                >
                  {template.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="caption-style"
            >
              Style
            </label>
            <select
              id="caption-style"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
              value={captionStyle}
              onChange={(event) => {
                setCaptionStyle(event.target.value);
                setSelectedCaptionTemplate("custom");
              }}
            >
              <option value="bold">Bold highlight</option>
              <option value="minimal">Minimal</option>
              <option value="karaoke">Karaoke</option>
            </select>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="caption-size"
            >
              Size
            </label>
            <input
              id="caption-size"
              type="range"
              min={14}
              max={36}
              value={captionSize}
              onChange={(event) => {
                setCaptionSize(Number(event.target.value));
                setSelectedCaptionTemplate("custom");
              }}
            />
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="caption-text-color"
            >
              Text
            </label>
            <select
              id="caption-text-color"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
              value={captionTextColor}
              onChange={(event) => {
                setCaptionTextColor(event.target.value);
                setSelectedCaptionTemplate("custom");
              }}
            >
              <option value="text-white">White</option>
              <option value="text-slate-100">Slate</option>
              <option value="text-amber-100">Amber</option>
            </select>
            <label
              className="text-xs uppercase tracking-wide text-slate-400"
              htmlFor="caption-bg-color"
            >
              Background
            </label>
            <select
              id="caption-bg-color"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
              value={captionBgColor}
              onChange={(event) => {
                setCaptionBgColor(event.target.value);
                setSelectedCaptionTemplate("custom");
              }}
            >
              <option value="bg-aurora/80">Aurora</option>
              <option value="bg-black/40">Shadow</option>
              <option value="bg-amber-500/20">Amber</option>
            </select>
          </div>
          <div className="md:col-span-2 rounded-xl border border-slate-800 bg-black/80 p-6 text-center">
            <span
              className={`inline-block px-3 py-2 font-semibold ${captionSizeClass} ${captionTextColor} ${captionBgColor} ${
                captionStyle === "bold"
                  ? "shadow-lg"
                  : captionStyle === "karaoke"
                  ? "tracking-wide"
                  : "opacity-90"
              }`}
            >
              Example captions appear here
            </span>
          </div>
        </div>
      ) : null}

      {automationTab === "editor" ? (
        <div className="mt-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div>
            <h3 className="text-lg font-semibold">Editor shell</h3>
            <p className="mt-1 text-xs text-slate-400">
              Open the editor workspace for timeline and clip tools.
            </p>
          </div>
          <a
            className="rounded-lg bg-aurora px-4 py-2 text-xs font-semibold text-slate-900"
            href={selectedProjectId ? `/editor/${selectedProjectId}` : "#"}
          >
            Open editor
          </a>
        </div>
      ) : null}

      {automationTab === "lab" ? (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() => handleTriggerFeature("/video/auto-clip", "Auto-clip")}
          >
            Auto-clip extraction
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() =>
              handleTriggerFeature("/video/transcribe", "Transcription")
            }
          >
            Transcription / edit by text
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() => handleTriggerFeature("/video/captions", "Captions")}
          >
            AI captions
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() => handleTriggerFeature("/video/lipsync", "Lip sync")}
          >
            Lip sync (visemes)
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() =>
              handleTriggerFeature("/video/multitrack", "Multitrack")
            }
          >
            Multitrack audio
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() =>
              handleTriggerFeature("/video/scene-detect", "Scene detection")
            }
          >
            Scene detection
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={() =>
              handleTriggerFeature("/video/templates", "Templates")
            }
          >
            Templates / brand kits
          </button>
        </div>
      ) : null}

      {automationTab === "exports" ? (
        <div className="mt-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            {[
              { key: "youtube", label: "YouTube" },
              { key: "tiktok", label: "TikTok" },
              { key: "instagram", label: "Instagram" },
              { key: "facebook", label: "Facebook" },
            ].map((preset) => (
              <button
                key={preset.key}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
                type="button"
                onClick={() => handleExportPreset(preset.key)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200"
            type="button"
            onClick={handleExportBatch}
          >
            Run batch export
          </button>
          {exportStatus ? (
            <p className="text-xs text-slate-400">{exportStatus}</p>
          ) : null}
          {exportQueue.length > 0 ? (
            <div className="space-y-2">
              {exportQueue.map((entry) => (
                <div
                  key={entry.preset}
                  className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs"
                >
                  <span className="uppercase text-slate-300">
                    {entry.preset}
                  </span>
                  <span className="text-slate-400">{entry.status}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );

  return (
    <div className="flex h-screen flex-col bg-midnight text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-4xl font-black tracking-wide text-white">
              Pro Creator
            </h1>
            <p className="mt-1 text-sm uppercase tracking-[0.3em] text-slate-400">
              Production Dashboard
            </p>
          </div>
          <div className="flex items-center gap-3">
            {accessAllowed ? (
              <button
                type="button"
                className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora"
                onClick={() => setShowAccountPanel((prev) => !prev)}
              >
                Credits & Plans
              </button>
            ) : (
              <a
                className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200"
                href="/login"
              >
                Sign in
              </a>
            )}
            <div
              className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-xs font-semibold text-emerald-200"
              suppressHydrationWarning
            >
              {hasMounted
                ? `Credits: ${creditsRemaining ?? "--"} left • used ${creditsUsed ?? "--"} / ${creditsTotal ?? "--"}`
                : "Credits: -- / --"}
            </div>
          </div>
        </div>
        {accessAllowed && showAccountPanel ? (
          <div className="mx-auto flex max-w-6xl justify-end px-6 pb-4">
            <div className="w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-white">Credits & account</p>
                  <p className="text-xs text-slate-400">
                    Buy credits, monitor usage, and manage account access.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {signedIn ? (
                    <button
                      type="button"
                      className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-200"
                      onClick={handleSignOut}
                    >
                      Sign out
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:text-slate-200"
                    onClick={() => setShowAccountPanel(false)}
                  >
                    Close
                  </button>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/40 p-1">
                <button
                  type="button"
                  className={`flex-1 rounded-lg px-3 py-2 text-[11px] font-semibold transition ${
                    accountTab === "plans"
                      ? "bg-slate-950/80 text-white"
                      : "text-slate-300 hover:text-white"
                  }`}
                  onClick={() => setAccountTab("plans")}
                >
                  Plans
                </button>
                <button
                  type="button"
                  className={`flex-1 rounded-lg px-3 py-2 text-[11px] font-semibold transition ${
                    accountTab === "access"
                      ? "bg-slate-950/80 text-white"
                      : "text-slate-300 hover:text-white"
                  }`}
                  onClick={() => setAccountTab("access")}
                >
                  Access
                </button>
              </div>

              {accountTab === "plans" ? (
                <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs text-slate-300" suppressHydrationWarning>
                    {hasMounted
                      ? `Balance: ${creditsRemaining ?? "--"} left • used ${creditsUsed ?? "--"} / ${creditsTotal ?? "--"}`
                      : "Balance: -- / --"}
                  </p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {plansLoading ? (
                      <p className="text-xs text-slate-400">Loading plans...</p>
                    ) : (
                      creditPlans.map((plan) => (
                        <div
                          key={plan.id}
                          className={`rounded-lg border p-3 ${
                            plan.popular
                              ? "border-aurora/60 bg-aurora/10"
                              : "border-slate-700 bg-slate-950/60"
                          }`}
                        >
                          <p className="text-sm font-semibold text-white">{plan.name}</p>
                          <p className="mt-1 text-xs text-slate-300">
                            {plan.credits.toLocaleString()} credits
                          </p>
                          <p className="text-xs text-slate-400">${plan.price_usd}</p>
                          <button
                            type="button"
                            className="mt-2 w-full rounded-md border border-aurora/50 px-2 py-1 text-xs font-semibold text-aurora"
                            onClick={() => handlePurchasePlan(plan.id)}
                            disabled={purchaseLoadingPlan === plan.id || !plan.checkout_enabled}
                          >
                            {purchaseLoadingPlan === plan.id
                              ? "Processing..."
                              : plan.checkout_enabled
                              ? "Buy"
                              : "Unavailable"}
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  {purchaseStatus ? (
                    <p className="mt-2 text-xs text-emerald-300">{purchaseStatus}</p>
                  ) : null}
                  <p className="mt-2 text-[11px] text-slate-500">
                    Live Stripe checkout enabled for configured plans.
                  </p>
                </div>
              ) : null}

              {accountTab === "access" ? (
                <div className="mt-3 space-y-4">
                  <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-white">Password gate</p>
                        <p className="mt-1 text-xs text-slate-400">
                          When enabled, the app requires a sign-in before any features can be used.
                        </p>
                        <p className="mt-2 text-[11px] text-slate-500" suppressHydrationWarning>
                          {authGateLoading
                            ? "Status: checking..."
                            : authGateStatus
                            ? `Status: ${authGateStatus.enabled ? "ON" : "OFF"} (source: ${authGateStatus.source})`
                            : "Status: unknown"}
                        </p>
                      </div>
                      <button
                        type="button"
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
                          authGateStatus?.enabled ? "bg-aurora" : "bg-slate-700"
                        } ${
                          authGateLocked || authGateLoading || authGateUpdating
                            ? "opacity-60"
                            : "hover:brightness-110"
                        }`}
                        aria-label="Toggle password gate"
                        disabled={authGateLocked || authGateLoading || authGateUpdating}
                        onClick={() => handlePasswordGateToggle(!(authGateStatus?.enabled ?? true))}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-slate-950 shadow transition ${
                            authGateStatus?.enabled ? "translate-x-6" : "translate-x-1"
                          }`}
                        />
                      </button>
                    </div>
                    {authGateLocked ? (
                      <p className="mt-2 text-[11px] text-slate-500">
                        Locked by `AUTH_REQUIRED=true` in the environment.
                      </p>
                    ) : null}
                    {authGateError ? (
                      <p className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                        {authGateError}
                      </p>
                    ) : null}
                    {authGateStatus?.enabled ? (
                      <p className="mt-2 text-[11px] text-slate-500">
                        Tip: update your password below, then enable the gate.
                      </p>
                    ) : (
                      <p className="mt-2 text-[11px] text-slate-500">
                        Gate is off by default for local testing. Turn it on when you&apos;re ready to require sign-in.
                      </p>
                    )}
                  </div>

                  <form className="space-y-3" onSubmit={handlePasswordChange}>
                    <p className="text-xs font-semibold text-white">Update password</p>
                    {authGateStatus?.enabled !== false ? (
                      <div>
                        <label className="text-xs text-slate-400" htmlFor="current-password">
                          Current password
                        </label>
                        <div className="relative mt-1">
                          <input
                            id="current-password"
                            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 pr-10 text-sm text-white"
                            type={showCurrentPassword ? "text" : "password"}
                            value={currentPassword}
                            onChange={(event) => setCurrentPassword(event.target.value)}
                          />
                          <button
                            type="button"
                            className="absolute inset-y-0 right-2 flex items-center text-slate-400 transition hover:text-slate-200"
                            aria-label={
                              showCurrentPassword ? "Hide current password" : "Show current password"
                            }
                            onClick={() => setShowCurrentPassword((value) => !value)}
                          >
                            {showCurrentPassword ? (
                              <svg
                                aria-hidden="true"
                                viewBox="0 0 24 24"
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M10.584 10.584a2 2 0 002.832 2.832"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M7.5 7.5C5.018 9.086 3.56 11.2 3 12c1.35 1.95 4.838 6 9 6 1.545 0 2.96-.474 4.125-1.178"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M14.12 14.12A3 3 0 009.88 9.88"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M9.35 5.85A8.497 8.497 0 0112 5c4.162 0 7.65 4.05 9 6-.51.737-1.528 2.097-2.975 3.357"
                                />
                              </svg>
                            ) : (
                              <svg
                                aria-hidden="true"
                                viewBox="0 0 24 24"
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M2.458 12C3.732 9.057 7.2 5.5 12 5.5c4.8 0 8.268 3.557 9.542 6-1.274 2.943-4.742 6.5-9.542 6.5-4.8 0-8.268-3.557-9.542-6z"
                                />
                                <circle cx="12" cy="12" r="3" />
                              </svg>
                            )}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-[11px] text-slate-500">
                        Gate is currently off, so you can set a new password without entering the old one.
                      </p>
                    )}
                    <div>
                      <label className="text-xs text-slate-400" htmlFor="new-password">
                        New password
                      </label>
                      <div className="relative mt-1">
                        <input
                          id="new-password"
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 pr-10 text-sm text-white"
                          type={showNewPassword ? "text" : "password"}
                          value={newPassword}
                          onChange={(event) => setNewPassword(event.target.value)}
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-2 flex items-center text-slate-400 transition hover:text-slate-200"
                          aria-label={showNewPassword ? "Hide new password" : "Show new password"}
                          onClick={() => setShowNewPassword((value) => !value)}
                        >
                          {showNewPassword ? (
                            <svg
                              aria-hidden="true"
                              viewBox="0 0 24 24"
                              className="h-4 w-4"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.5"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M10.584 10.584a2 2 0 002.832 2.832"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M7.5 7.5C5.018 9.086 3.56 11.2 3 12c1.35 1.95 4.838 6 9 6 1.545 0 2.96-.474 4.125-1.178"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M14.12 14.12A3 3 0 009.88 9.88"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M9.35 5.85A8.497 8.497 0 0112 5c4.162 0 7.65 4.05 9 6-.51.737-1.528 2.097-2.975 3.357"
                              />
                            </svg>
                          ) : (
                            <svg
                              aria-hidden="true"
                              viewBox="0 0 24 24"
                              className="h-4 w-4"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.5"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M2.458 12C3.732 9.057 7.2 5.5 12 5.5c4.8 0 8.268 3.557 9.542 6-1.274 2.943-4.742 6.5-9.542 6.5-4.8 0-8.268-3.557-9.542-6z"
                              />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-slate-400" htmlFor="confirm-password">
                        Confirm password
                      </label>
                      <div className="relative mt-1">
                        <input
                          id="confirm-password"
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 pr-10 text-sm text-white"
                          type={showConfirmPassword ? "text" : "password"}
                          value={confirmPassword}
                          onChange={(event) => setConfirmPassword(event.target.value)}
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-2 flex items-center text-slate-400 transition hover:text-slate-200"
                          aria-label={
                            showConfirmPassword ? "Hide confirm password" : "Show confirm password"
                          }
                          onClick={() => setShowConfirmPassword((value) => !value)}
                        >
                          {showConfirmPassword ? (
                            <svg
                              aria-hidden="true"
                              viewBox="0 0 24 24"
                              className="h-4 w-4"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.5"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M10.584 10.584a2 2 0 002.832 2.832"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M7.5 7.5C5.018 9.086 3.56 11.2 3 12c1.35 1.95 4.838 6 9 6 1.545 0 2.96-.474 4.125-1.178"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M14.12 14.12A3 3 0 009.88 9.88"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M9.35 5.85A8.497 8.497 0 0112 5c4.162 0 7.65 4.05 9 6-.51.737-1.528 2.097-2.975 3.357"
                              />
                            </svg>
                          ) : (
                            <svg
                              aria-hidden="true"
                              viewBox="0 0 24 24"
                              className="h-4 w-4"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.5"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M2.458 12C3.732 9.057 7.2 5.5 12 5.5c4.8 0 8.268 3.557 9.542 6-1.274 2.943-4.742 6.5-9.542 6.5-4.8 0-8.268-3.557-9.542-6z"
                              />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </div>
                    {passwordError ? (
                      <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                        {passwordError}
                      </p>
                    ) : null}
                    {passwordStatus ? (
                      <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                        {passwordStatus}
                      </p>
                    ) : null}
                    <button
                      className="w-full rounded-lg bg-aurora px-3 py-2 text-xs font-semibold text-slate-900 transition hover:bg-aurora/90"
                      type="submit"
                      disabled={passwordLoading}
                    >
                      {passwordLoading ? "Updating..." : "Update password"}
                    </button>
                  </form>

                  {signedIn ? (
                    <button
                      type="button"
                      className="w-full rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-slate-500"
                      onClick={handleSignOut}
                    >
                      Sign out now
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <aside className="w-60 min-h-0 overflow-y-auto border-r border-slate-800 bg-slate-950/80 px-4 py-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Navigation
            </p>
            <div className="mt-3 space-y-1.5">
              {panels.map((panel) => (
                <button
                  key={panel.id}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-xs font-semibold transition ${
                    activePanel === panel.id
                      ? "border-aurora/40 bg-aurora/10 text-aurora"
                      : "border-slate-800 text-slate-300 hover:border-slate-600"
                  }`}
                  type="button"
                  onClick={() => setActivePanel(panel.id)}
                >
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden="true">{panel.icon}</span>
                    {panel.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div className="mt-5">
            <label className="text-xs uppercase tracking-wide text-slate-500">
              Active project
            </label>
            <select
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs"
              aria-label="Active project"
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
            >
              <option value="">Select project</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.title}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-5 space-y-2 text-xs">
            <button
              className="w-full rounded-lg border border-aurora/40 px-3 py-2 text-aurora"
              type="button"
              onClick={handleEnqueueJob}
              disabled={!selectedProjectId || queueLoading}
            >
              Queue job
            </button>
            <button
              className="w-full rounded-lg border border-slate-700 px-3 py-2 text-slate-200"
              type="button"
              onClick={handleProcessQueue}
              disabled={queueLoading}
            >
              Process next
            </button>
            <button
              className={`w-full rounded-lg border px-3 py-2 ${
                runnerRunning
                  ? "border-red-500/40 text-red-200"
                  : "border-aurora/40 text-aurora"
              }`}
              type="button"
              onClick={handleRunnerToggle}
              disabled={queueLoading}
            >
              {runnerRunning ? "Stop runner" : "Run continuously"}
            </button>
          </div>
        </aside>

        <main className="flex-1 min-h-0 overflow-y-auto">
          <div className="space-y-4 px-4 py-4 text-sm">
            {activePanel === "overview" ? (
              <section className="grid gap-4">
                <div className="grid gap-4 md:grid-cols-2">
                  {[
                    {
                      title: "Script Engine",
                      detail: "Generate structured scripts and scenes.",
                      tab: "script",
                    },
                    {
                      title: "Voice Engine",
                      detail: "Produce narration and voice assets.",
                      tab: "voice",
                    },
                    {
                      title: "Image Engine",
                      detail: "Create scene visuals and thumbnails.",
                      tab: "image",
                    },
                    {
                      title: "Video Engine",
                      detail: "Render final videos with transitions.",
                      tab: "video",
                    },
                  ].map((card) => (
                    <div
                      key={card.title}
                      className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5"
                    >
                      <h3 className="text-lg font-semibold text-white">
                        {card.title}
                      </h3>
                      <p className="mt-2 text-sm text-slate-400">
                        {card.detail}
                      </p>
                      <button
                        className="mt-4 rounded-lg border border-aurora/40 px-3 py-2 text-xs text-aurora"
                        type="button"
                        onClick={() => {
                          setActivePanel("engines");
                          setEnginesTab(card.tab);
                        }}
                      >
                        Open in Engines
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {activePanel === "projects" ? (
              <section className="grid gap-4 lg:grid-cols-[1fr_1.4fr] lg:h-[calc(100dvh-10rem)] lg:min-h-0">
                <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 lg:sticky lg:top-4 lg:self-start">
                  <h2 className="text-xl font-semibold">Create a new project</h2>
                  <p className="mt-2 text-sm text-slate-400">
                    Start a production run by registering a project. The backend
                    will create folders and metadata.
                  </p>
                  <form className="mt-6 space-y-4" onSubmit={handleCreate}>
                    <div>
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Title
                      </label>
                      <input
                        className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white"
                        placeholder="High-converting sales video"
                        value={title}
                        onChange={(event) => setTitle(event.target.value)}
                        required
                      />
                    </div>
                    <div>
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Topic
                      </label>
                      <input
                        className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white"
                        placeholder="AI tools for creators"
                        value={topic}
                        onChange={(event) => setTopic(event.target.value)}
                        required
                      />
                    </div>
                    <button
                      className="w-full rounded-xl bg-aurora px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-aurora/90"
                      type="submit"
                      disabled={createLoading}
                    >
                      {createLoading ? "Creating..." : "Create project"}
                    </button>
                  </form>
                  {error ? (
                    <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                      {error}
                    </p>
                  ) : null}
                </div>

                <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 flex min-h-0 flex-col lg:h-full">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-semibold">
                        Project pipeline status
                      </h2>
                      <p className="mt-2 text-sm text-slate-400">
                        These show the projects currently registered in the backend.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                      <button
                        className="rounded-full border border-red-500/40 px-3 py-1 text-red-200"
                        type="button"
                        onClick={handleDeleteAllProjects}
                        disabled={pipelineLoading}
                      >
                        {pipelineLoading ? "Working..." : "Delete all projects"}
                      </button>
                      <div className="flex items-center gap-2 rounded-full border border-aurora/50 px-3 py-1">
                        <button
                          className="text-aurora"
                          type="button"
                          onClick={handlePurgeStaleProjects}
                          disabled={pipelineLoading}
                        >
                          {pipelineLoading
                            ? "Working..."
                            : `Auto-clean (${stalePurgeDays}d+)`}
                        </button>
                        <input
                          className="w-12 bg-transparent text-[10px] text-aurora"
                          type="number"
                          min={7}
                          aria-label="Stale project days"
                          value={stalePurgeDays}
                          onChange={(event) =>
                            setStalePurgeDays(Number(event.target.value))
                          }
                        />
                      </div>
                    </div>
                  </div>
                  {pipelineMessage ? (
                    <p className="mt-3 text-xs text-emerald-300">
                      {pipelineMessage}
                    </p>
                  ) : null}
                  {pipelineError ? (
                    <p className="mt-3 text-xs text-red-300">{pipelineError}</p>
                  ) : null}
                  <div className="mt-6 min-h-0 flex-1 overflow-y-auto pr-1">
                    {loading ? (
                      <p className="text-sm text-slate-500">Loading projects…</p>
                    ) : (
                      <div className="grid gap-4">
                        {projects.length === 0 ? (
                          <div className="rounded-xl border border-dashed border-slate-700 p-6 text-sm text-slate-400">
                            No projects yet. Create one to get started.
                          </div>
                        ) : (
                          projects.map((project) => (
                            <ProjectCard
                              key={project.project_id}
                              project={project}
                              scriptRefreshToken={scriptRefreshToken}
                              onScriptCleared={() => {
                                setScriptResult(null);
                                setScriptEditText("");
                              }}
                              onProjectDeleted={(projectId) =>
                                setProjects((prev) =>
                                  prev.filter((item) => item.project_id !== projectId)
                                )
                              }
                            />
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </section>
            ) : null}

            {activePanel === "engines" ? renderEnginesSection() : null}
            {activePanel === "automation" ? renderAutomationSection() : null}

            {activePanel === "orchestration" ? (
              <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold">Orchestration status</h2>
                    <p className="mt-1 text-sm text-slate-400">
                      Queue, schedules, and continuous runner controls.
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                      Script queue
                    </p>
                    <div className="mt-3 grid gap-2 text-xs">
                      <select
                        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                        aria-label="Queue job type"
                        value={queueKind}
                        onChange={(event) => setQueueKind(event.target.value)}
                      >
                        <option value="full">Full pipeline</option>
                        <option value="script">Script only</option>
                        <option value="voice">Voice only</option>
                        <option value="image">Image only</option>
                        <option value="render">Render video</option>
                        <option value="export">Export preset</option>
                      </select>
                      <input
                        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                        placeholder="Topic override"
                        value={queueTopic}
                        onChange={(event) => setQueueTopic(event.target.value)}
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                          type="number"
                          min={0.25}
                          step={0.05}
                          aria-label="Duration minutes"
                          value={queueDuration}
                          onChange={(event) =>
                            setQueueDuration(Number(event.target.value))
                          }
                        />
                        <select
                          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                          aria-label="Tone"
                          value={queueTone}
                          onChange={(event) => setQueueTone(event.target.value)}
                        >
                          <option value="neutral">Neutral</option>
                          <option value="inspiring">Inspiring</option>
                          <option value="bold">Bold</option>
                          <option value="cinematic">Cinematic</option>
                        </select>
                      </div>
                      <input
                        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                        placeholder="Export preset"
                        value={queuePreset}
                        onChange={(event) => setQueuePreset(event.target.value)}
                      />
                      <input
                        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                        type="number"
                        min={1}
                        aria-label="Batch count"
                        value={batchCount}
                        onChange={(event) => setBatchCount(Number(event.target.value))}
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          className="rounded-lg border border-aurora/40 px-3 py-2 text-aurora"
                          type="button"
                          onClick={handleEnqueueJob}
                          disabled={queueLoading}
                        >
                          Queue job
                        </button>
                        <button
                          className="rounded-lg border border-slate-700 px-3 py-2 text-slate-200"
                          type="button"
                          onClick={handleEnqueueBatch}
                          disabled={queueLoading}
                        >
                          Batch ({batchCount})
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                      Scheduler
                    </p>
                    <div className="mt-3 space-y-2 text-xs">
                      <label className="text-slate-400">Cadence (days)</label>
                      <input
                        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2"
                        type="number"
                        min={1}
                        aria-label="Schedule cadence days"
                        value={scheduleCadence}
                        onChange={(event) =>
                          setScheduleCadence(Number(event.target.value))
                        }
                      />
                      <button
                        className="w-full rounded-lg border border-aurora/40 px-3 py-2 text-aurora"
                        type="button"
                        onClick={handleCreateSchedule}
                        disabled={queueLoading}
                      >
                        Create schedule
                      </button>
                      <button
                        className="w-full rounded-lg border border-slate-700 px-3 py-2 text-slate-200"
                        type="button"
                        onClick={handleRunSchedules}
                        disabled={queueLoading}
                      >
                        Run schedules
                      </button>
                    </div>
                  </div>
                </div>
                {queueStatus ? (
                  <p className="mt-3 text-xs text-emerald-300">{queueStatus}</p>
                ) : null}
                {queueError ? (
                  <p className="mt-3 text-xs text-red-300">{queueError}</p>
                ) : null}
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                      Queue
                    </p>
                    <div className="mt-2 space-y-2 text-xs">
                      {queueItems.length === 0 ? (
                        <p className="text-slate-400">No queued jobs yet.</p>
                      ) : (
                        queueItems.slice(0, 6).map((item) => (
                          <div
                            key={item.id}
                            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2"
                          >
                            <div>
                              <p className="text-slate-200">
                                {item.kind} · {item.status}
                              </p>
                              <p className="text-[10px] text-slate-400">
                                Attempts {item.attempts}/{item.max_attempts}
                              </p>
                            </div>
                            {item.status === "failed" ? (
                              <button
                                className="rounded-lg border border-aurora/40 px-2 py-1 text-[10px] text-aurora"
                                type="button"
                                onClick={() => handleRetryJob(item.id)}
                                disabled={queueLoading}
                              >
                                Retry
                              </button>
                            ) : null}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                      Schedules
                    </p>
                    <div className="mt-2 space-y-2 text-xs">
                      {scheduleItems.length === 0 ? (
                        <p className="text-slate-400">No schedules yet.</p>
                      ) : (
                        scheduleItems.slice(0, 4).map((item) => (
                          <div
                            key={item.id}
                            className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2"
                          >
                            <p className="text-slate-200">
                              Every {item.cadence_days}d · Next{" "}
                              {new Date(item.next_run_at).toLocaleString()}
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </section>
            ) : null}

            {activePanel === "logs" ? (
              <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold">Engine activity log</h2>
                    <p className="mt-1 text-sm text-slate-400">
                      Recent actions from the orchestration layer.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    {([
                      { key: "all", label: "All" },
                      { key: "ok", label: "OK" },
                      { key: "error", label: "Errors" },
                    ] as const).map((filter) => (
                      <button
                        key={filter.key}
                        className={`rounded-full border px-3 py-1 ${
                          logFilter === filter.key
                            ? "border-aurora/40 bg-aurora/10 text-aurora"
                            : "border-slate-700 text-slate-300"
                        }`}
                        type="button"
                        onClick={() => setLogFilter(filter.key)}
                      >
                        {filter.label}
                      </button>
                    ))}
                    <button
                      className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300"
                      type="button"
                      onClick={handleCopyLogs}
                    >
                      Copy
                    </button>
                    <button
                      className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300"
                      type="button"
                      onClick={handleExportLogs}
                    >
                      Export
                    </button>
                    <button
                      className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300"
                      type="button"
                      onClick={() => setActionLogs([])}
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 text-xs md:grid-cols-3">
                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
                    <p className="text-slate-400">Total events</p>
                    <p className="text-sm font-semibold text-white">{logStats.total}</p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
                    <p className="text-slate-400">OK events</p>
                    <p className="text-sm font-semibold text-emerald-200">
                      {logStats.ok}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
                    <p className="text-slate-400">Error events</p>
                    <p className="text-sm font-semibold text-red-200">
                      {logStats.errors}
                    </p>
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  {filteredLogs.length === 0 ? (
                    <p className="text-sm text-slate-400">No activity yet.</p>
                  ) : (
                    filteredLogs.slice(0, 10).map((entry, index) => (
                      <div
                        key={`${entry.timestamp}-${index}`}
                        className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs"
                      >
                        <span className="text-slate-300">{entry.message}</span>
                        <span
                          className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wide ${
                            entry.status === "ok"
                              ? "bg-aurora/20 text-aurora"
                              : "bg-red-500/20 text-red-200"
                          }`}
                        >
                          {entry.engine}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </section>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}
