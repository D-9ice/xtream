"use client";

import { FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  CommunityPost,
  BillingReceipt,
  BillingTransactionRecord,
  CreditBalance,
  CreditPlan,
  OrchestrationRunnerStatus,
  enqueueOrchestrationJob,
  SocialAccountConnection,
  SocialPublishJob,
  fetchOrchestrationRunnerStatus,
  WorkflowCharacterList,
  WorkflowLibrary,
  WorkflowProject,
  WorkflowProductionStatus,
  WorkflowState,
  approveWorkflowCharacters,
  approveWorkflowScript,
  archiveWorkflowProject,
  autoCreateWorkflowProject,
  applaudCommunityPost,
  createWorkflowCharacter,
  createWorkflowProject,
  createLibraryCharacter,
  createStripeCheckoutSession,
  duplicateWorkflowProject,
  deleteWorkflowProjects,
  fetchMyCredits,
  fetchCreditPlans,
  createCommunityPost,
  fetchCommunityPosts,
  deleteSocialConnection,
  fetchBillingReceipts,
  fetchBillingTransactionRecords,
  deleteBillingReceipt,
  fetchWorkflowCharacters,
  fetchWorkflowLibrary,
  fetchWorkflowProductionSummary,
  fetchWorkflowProductionStatus,
  fetchWorkflowProject,
  fetchWorkflowProjects,
  fetchSocialConnections,
  fetchSocialPublishJobs,
  generateWorkflowCharacter,
  generateLibraryCharacter,
  generateWorkflowScript,
  purchaseCharacterSlotPack,
  publishSocialVideos,
  regenerateWorkflowScript,
  retryWorkflowProduction,
  selectWorkflowCharacters,
  startOrchestrationRunner,
  startWorkflowProduction,
  saveSocialConnection,
  submitWorkflowFeedback,
  stopOrchestrationRunner,
  updateWorkflowScript,
  uploadWorkflowCharacter,
  uploadLibraryCharacter,
} from "../lib/api";

type NavItem =
  | "overview"
  | "projects"
  | "create"
  | "auto-create"
  | "library"
  | "publish"
  | "transaction-records"
  | "downloads"
  | "play"
  | "community"
  | "feedback"
  | "factory-mode";
type LibraryTab = "characters" | "scripts" | "videos";
type CharacterRoleFilter = "all" | "main" | "supporting" | "extra" | "npc";
type BillingProvider = "stripe" | "paystack";
type AutoCreateCharacterDraft = {
  id: string;
  name: string;
  role_type: CharacterRoleFilter | "main" | "supporting" | "extra" | "npc";
  description: string;
};

const MAIN_NAV_ITEMS: Array<{ id: NavItem; label: string }> = [
  { id: "auto-create", label: "Auto-Create" },
  { id: "downloads", label: "Download" },
  { id: "factory-mode", label: "Factory Mode" },
  { id: "library", label: "Library" },
  { id: "create", label: "Manual-Create" },
  { id: "overview", label: "Overview" },
  { id: "play", label: "Playback" },
  { id: "projects", label: "Projects" },
  { id: "publish", label: "Publish" },
  { id: "transaction-records", label: "Transaction Records" },
];

const FOOTER_NAV_ITEMS: Array<{ id: NavItem; label: string }> = [
  { id: "feedback", label: "User Feedback" },
  { id: "community", label: "X'treamers" },
];

const ALL_NAV_ITEMS = [...MAIN_NAV_ITEMS, ...FOOTER_NAV_ITEMS];
const NAV_ITEMS = MAIN_NAV_ITEMS;
const XTREAM_LOGO_SRC = "/xtream-logo.png";
const VIDEO_READY_MESSAGE = "VIDEO READY";
const FACTORY_MODE_ENABLED = process.env.NEXT_PUBLIC_FACTORY_MODE_ENABLED === "true";

const STEPS = [
  "Story Request",
  "Review Script",
  "Choose Characters",
  "Produce Video",
];

const SOCIAL_PLATFORM_OPTIONS = [
  { key: "youtube", label: "YouTube" },
  { key: "instagram", label: "Instagram" },
  { key: "facebook", label: "Facebook" },
  { key: "x", label: "X" },
  { key: "tiktok", label: "TikTok" },
] as const;

function SocialPlatformMark({ platform }: { platform: SocialAccountConnection["platform"] }) {
  const instagramGradientId = useId();
  switch (platform) {
    case "youtube":
      return (
        <svg viewBox="0 0 24 24" className="h-[36px] w-[36px]" aria-hidden="true">
          <rect x="2.5" y="5.5" width="19" height="13" rx="4.25" fill="#ff0033" />
          <path d="M10.1 8.8 16 12l-5.9 3.2V8.8Z" fill="#fff" />
        </svg>
      );
    case "instagram":
      return (
        <svg viewBox="0 0 24 24" className="h-[36px] w-[36px]" aria-hidden="true">
          <defs>
            <linearGradient id={instagramGradientId} x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#feda75" />
              <stop offset="26%" stopColor="#fa7e1e" />
              <stop offset="52%" stopColor="#d62976" />
              <stop offset="76%" stopColor="#962fbf" />
              <stop offset="100%" stopColor="#4f5bd5" />
            </linearGradient>
          </defs>
          <rect x="3.25" y="3.25" width="17.5" height="17.5" rx="5" fill={`url(#${instagramGradientId})`} />
          <rect x="7.1" y="7.1" width="9.8" height="9.8" rx="3.1" stroke="#fff" strokeWidth="1.7" fill="none" />
          <circle cx="12" cy="12" r="2.6" fill="#fff" />
          <circle cx="16.75" cy="7.25" r="1" fill="#fff" />
        </svg>
      );
    case "facebook":
      return (
        <svg viewBox="0 0 24 24" className="h-[36px] w-[36px]" aria-hidden="true">
          <circle cx="12" cy="12" r="10" fill="#1877f2" />
          <path d="M13.4 20v-6.7h2.2l.4-2.9h-2.6V8.2c0-.8.2-1.4 1.5-1.4H16V4.6c-.4 0-1.2-.1-2.2-.1-2.1 0-3.6 1.3-3.6 3.7v2.2H7.8v2.9h2.4V20h3.2Z" fill="#fff" />
        </svg>
      );
    case "x":
      return (
        <svg viewBox="0 0 24 24" className="h-[36px] w-[36px]" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5.5" fill="#000" />
          <path d="M6 5.2h3.4l4.4 5.6 4.4-5.6h2.2l-5.4 6.8L19 18.8h-3.4l-4.8-6.1-4.7 6.1H4l5.8-7.4L6 5.2Z" fill="#fff" />
        </svg>
      );
    case "tiktok":
      return (
        <svg viewBox="0 0 24 24" className="h-[36px] w-[36px]" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5" fill="#000" />
          <path
            d="M13.5 4.3c.3 1.6 1.2 2.9 2.8 3.4v2.2c-1.3-.1-2.5-.5-3.6-1.2v4.5c0 2.6-1.9 4.8-4.5 5.1-2.7.2-5.1-1.8-5.1-4.4 0-2.7 2.4-4.7 5.1-4.4v2.1c-1.2-.1-2.3.7-2.5 2-.1 1.3.9 2.5 2.2 2.5 1.2 0 2.2-.9 2.2-2.1V4.3h3.4Z"
            fill="#25f4ee"
            transform="translate(0.35 0.35)"
          />
          <path
            d="M13.5 4.3c.3 1.6 1.2 2.9 2.8 3.4v2.2c-1.3-.1-2.5-.5-3.6-1.2v4.5c0 2.6-1.9 4.8-4.5 5.1-2.7.2-5.1-1.8-5.1-4.4 0-2.7 2.4-4.7 5.1-4.4v2.1c-1.2-.1-2.3.7-2.5 2-.1 1.3.9 2.5 2.2 2.5 1.2 0 2.2-.9 2.2-2.1V4.3h3.4Z"
            fill="#fe2c55"
            transform="translate(1.05 -0.35)"
          />
          <path
            d="M13.5 4.3c.3 1.6 1.2 2.9 2.8 3.4v2.2c-1.3-.1-2.5-.5-3.6-1.2v4.5c0 2.6-1.9 4.8-4.5 5.1-2.7.2-5.1-1.8-5.1-4.4 0-2.7 2.4-4.7 5.1-4.4v2.1c-1.2-.1-2.3.7-2.5 2-.1 1.3.9 2.5 2.2 2.5 1.2 0 2.2-.9 2.2-2.1V4.3h3.4Z"
            fill="#fff"
          />
        </svg>
      );
    default:
      return null;
  }
}

const AUTO_CREATE_MAX_CUSTOM_CHARACTERS = 10;
const WORKFLOW_LOAD_TIMEOUT_MS = 12000;

function createAutoCreateCharacterDraft(): AutoCreateCharacterDraft {
  return {
    id: (globalThis.crypto?.randomUUID?.() ?? `char-${Date.now()}-${Math.random().toString(16).slice(2)}`),
    name: "",
    role_type: "supporting",
    description: "",
  };
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      globalThis.setTimeout(() => reject(new Error(`${label} timed out`)), timeoutMs);
    }),
  ]);
}

function socialPlatformLabel(platform: string): string {
  return SOCIAL_PLATFORM_OPTIONS.find((item) => item.key === platform)?.label ?? platform;
}

function socialPlatformIdentifierLabel(platform: string): string {
  switch (platform) {
    case "youtube":
      return "Channel ID or destination label";
    case "instagram":
      return "Instagram user id";
    case "facebook":
      return "Facebook page id";
    case "x":
      return "X account handle or user id";
    case "tiktok":
      return "TikTok username or account id";
    default:
      return "Account identifier";
  }
}

function billingProviderLabel(provider: BillingProvider): string {
  return provider === "paystack" ? "Paystack" : "Stripe";
}

function paymentProviderLabel(provider: BillingProvider): string {
  return provider === "paystack" ? "Paystack / MoMo" : "Stripe";
}

function paymentProviderPillClasses(provider: BillingProvider): string {
  return provider === "paystack"
    ? "border-blue-400/95 bg-blue-900/90 text-[#7aaaf7] shadow-[0_0_0_1px_rgba(59,130,246,0.26),0_0_14px_rgba(59,130,246,0.18)]"
    : "border-purple-400/70 bg-purple-950/90 text-purple-300";
}

function receiptProviderPillClasses(provider: BillingProvider | string | null | undefined): string {
  return provider === "paystack"
    ? "border-blue-400/70 bg-blue-950/80 text-blue-300"
    : "border-purple-400/60 bg-purple-950/80 text-purple-300";
}

function paymentProviderToggleText(): React.ReactNode {
  return (
    <>
      <span className="text-blue-500">PAYSTACK</span>
      <span className="text-white"> / </span>
      <span className="text-purple-400">STRIPE</span>
    </>
  );
}

function detectBrowserPreferredBillingProvider(): BillingProvider {
  if (typeof window === "undefined") {
    return "stripe";
  }
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  const locale = window.navigator.language.toLowerCase();
  const isGhanaLocale = locale.endsWith("-gh") || locale === "gh" || locale.startsWith("gh-");
  return timeZone === "Africa/Accra" || isGhanaLocale ? "paystack" : "stripe";
}

function checkoutProvidersForPlan(plan: CreditPlan): BillingProvider[] {
  const providers = (plan.checkout_providers ?? []).filter(
    (provider): provider is BillingProvider => provider === "stripe" || provider === "paystack"
  );
  if (providers.length > 0) {
    return providers;
  }
  return plan.checkout_enabled ? ["stripe"] : [];
}

function isFactoryAccessPlan(plan: CreditPlan): boolean {
  return (plan.kind ?? "credits") === "factory_access";
}

function factoryAccessPlanLabel(plan: CreditPlan): string {
  if (!isFactoryAccessPlan(plan)) {
    return `${plan.credits.toLocaleString()} credits`;
  }
  if (plan.access_mode === "subscription") {
    const durationDays = plan.access_days ?? 30;
    return `${durationDays}-day access`;
  }
  return "Lifetime access";
}

function selectedBillingPlanSummary(plan: CreditPlan): string {
  if (!isFactoryAccessPlan(plan)) {
    return `${plan.credits.toLocaleString()} credits for $${plan.price_usd}. Choose your payment route, then continue.`;
  }
  const accessMode = plan.access_mode === "subscription" ? "subscription" : "one-time";
  const accessLabel = accessMode === "subscription" ? `${plan.access_days ?? 30}-day` : "lifetime";
  return `Factory Mode ${accessLabel} access for $${plan.price_usd}. Choose your payment route, then continue.`;
}

function factoryAccessPurchaseLabel(plan: CreditPlan): string {
  return plan.access_mode === "subscription" ? "Subscribe" : "Unlock";
}

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

function inferPreferredBillingProvider(availableProviders: BillingProvider[]): BillingProvider | null {
  if (availableProviders.length === 0) {
    return null;
  }
  if (typeof window !== "undefined") {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
    const locale = window.navigator.language.toLowerCase();
    const isGhanaLocale = locale.endsWith("-gh") || locale === "gh" || locale.startsWith("gh-");
    if ((timeZone === "Africa/Accra" || isGhanaLocale) && availableProviders.includes("paystack")) {
      return "paystack";
    }
  }
  if (availableProviders.includes("stripe")) {
    return "stripe";
  }
  return availableProviders[0] ?? null;
}

type AutoCreateGenreOption = {
  value: string;
  label: string;
  factoryOnly?: boolean;
  developmentOnly?: boolean;
};

const AUTO_CREATE_GENRE_OPTIONS: AutoCreateGenreOption[] = [
  { value: "3D Anime", label: "3D Anime" },
  { value: "Action", label: "Action" },
  { value: "African Drama", label: "African Drama" },
  { value: "Adventure", label: "Adventure" },
  { value: "Cartoons", label: "Cartoons" },
  { value: "Comedy", label: "Comedy" },
  { value: "Detective / Investigative", label: "Detective / Investigative" },
  { value: "Documentary", label: "Documentary" },
  { value: "Drama", label: "Drama" },
  { value: "Fantasy", label: "Fantasy" },
  { value: "Historical", label: "Historical" },
  { value: "Horror", label: "Horror" },
  { value: "Mystery", label: "Mystery" },
  { value: "PodCast", label: "PodCast" },
  { value: "Real Events", label: "Real Events" },
  { value: "Religion", label: "Religion" },
  { value: "Romance", label: "Romance" },
  { value: "Sci-Fi", label: "Sci-Fi" },
  {
    value: "Series Video Maker (Factory Mode Only)",
    label: "Series Video Maker (Factory Mode Only)",
  },
  { value: "SitComs", label: "SitComs" },
  { value: "Thriller", label: "Thriller" },
  { value: "True Story", label: "True Story" },
];

const AUTO_CREATE_GENRES = [
  ...AUTO_CREATE_GENRE_OPTIONS.sort((left, right) =>
    left.value.localeCompare(right.value, undefined, { numeric: true, sensitivity: "base" })
  ),
  { value: "Wildlife/Animals", label: "Wildlife/Animals" },
];

function WildlifeGenreMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4 text-white"
      fill="currentColor"
    >
      <path d="M7.5 12.5c-1.1 0-2-.9-2-2 0-.8.5-1.6 1.2-1.9.4-.2.8-.2 1.2-.1.1-.3.3-.7.6-.9.3-.3.7-.5 1.2-.5.6 0 1.1.3 1.5.7.2.2.3.4.4.7.2-.2.4-.4.7-.5.4-.2.8-.2 1.2-.1.1-.3.3-.7.6-.9.3-.3.7-.5 1.2-.5.6 0 1.1.2 1.5.7.4.4.7 1 .7 1.6 0 .3 0 .5-.1.8.3.1.6.3.9.5.6.4.9 1 .9 1.7 0 1.1-.9 2-2 2-.4 0-.8-.1-1.1-.3-.4.8-1.2 1.3-2.1 1.3-.8 0-1.5-.4-1.9-1-.4.6-1.1 1-1.9 1-.9 0-1.7-.5-2.1-1.3-.3.2-.7.3-1.1.3ZM6 16.4c0-.8.6-1.4 1.4-1.4h9.2c.8 0 1.4.6 1.4 1.4 0 1.2-.6 2.4-1.5 3.1-.8.6-1.8.9-2.8.9h-3.4c-1 0-2-.3-2.8-.9C6.6 18.8 6 17.6 6 16.4Z" />
    </svg>
  );
}

function currentWorkflowStepLabel(project: WorkflowProject | null): string {
  return STEPS[workflowStageIndex(project)] ?? STEPS[0];
}

function workflowProgressPercent(project: WorkflowProject | null): number {
  if (!project) {
    return 0;
  }
  switch (project.workflow_state) {
    case "draft":
      return 6;
    case "script_generating":
      return 18;
    case "script_generated":
      return 32;
    case "script_approved":
      return 48;
    case "characters_in_progress":
      return 62;
    case "characters_approved":
      return 72;
    case "production_ready":
      return 82;
    case "production_queued":
      return 88;
    case "production_running":
      return 96;
    case "video_completed":
      return 100;
    case "production_failed":
      return 90;
    default:
      return 0;
  }
}

function workflowProgressCopy(project: WorkflowProject | null): {
  label: string;
  detail: string;
  tone: "info" | "warning" | "success" | "danger";
} {
  if (!project) {
    return {
      label: "No active project selected",
      detail: "Choose a project to track script, cast, and video production progress.",
      tone: "info",
    };
  }
  switch (project.workflow_state) {
    case "draft":
      return {
        label: "Story request",
        detail: "Enter your title and generate the first draft to begin.",
        tone: "warning",
      };
    case "script_generating":
      return {
        label: "Script generating",
        detail: "The draft is being built from your story request.",
        tone: "info",
      };
    case "script_generated":
      return {
        label: "Script ready for review",
        detail: "Approve the script to unlock character selection.",
        tone: "warning",
      };
    case "script_approved":
      return {
        label: "Characters next",
        detail: "Choose the cast and approve the character package.",
        tone: "info",
      };
    case "characters_in_progress":
      return {
        label: "Character work in progress",
        detail: "Select or generate the cast before production can begin.",
        tone: "info",
      };
    case "characters_approved":
      return {
        label: "Final approval needed",
        detail: "Confirm the approved script and cast to unlock video production.",
        tone: "warning",
      };
    case "production_ready":
      return {
        label: "Ready for production",
        detail: "Start rendering when you're ready to spend the estimated credits.",
        tone: "success",
      };
    case "production_queued":
      return {
        label: "Production queued",
        detail: "Your approved package is waiting for render capacity.",
        tone: "info",
      };
    case "production_running":
      return {
        label: "Rendering video",
        detail: "Scenes, voice, and the final render are being assembled now.",
        tone: "info",
      };
    case "production_failed":
      return {
        label: "Production needs a retry",
        detail: "Review the error and requeue the render from Step 4.",
        tone: "danger",
      };
    case "video_completed":
      return {
        label: VIDEO_READY_MESSAGE,
        detail: "Open Play or Download to continue.",
        tone: "success",
      };
    default:
      return {
        label: workflowStageLabel(project.workflow_state),
        detail: "Track the current workflow stage here.",
        tone: "info",
      };
  }
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
    return "border-white/95 bg-white/5 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_0_14px_rgba(255,255,255,0.12),0_0_18px_rgba(125,211,252,0.48),0_0_34px_rgba(59,130,246,0.40),0_0_52px_rgba(37,99,235,0.24)]";
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

function nextUnlockCopy(project: WorkflowProject | null): string {
  if (!project) {
    return "Generate the first script draft to unlock Review Script.";
  }
  if (!(project.script_approved || "").trim()) {
    return "Script approval unlocks character selection.";
  }
  if (!project.character_package_approved) {
    return "Character approval unlocks video production.";
  }
  if (project.workflow_state === "production_failed") {
    return "Retry production from Step 4 with the same approved package.";
  }
  if (project.workflow_state === "video_completed") {
    return "The final video is ready in this project and in Library.";
  }
  return "Final approval unlocks video production.";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeNav, setActiveNav] = useState<NavItem>("create");
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("characters");
  const [projects, setProjects] = useState<WorkflowProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<WorkflowProject | null>(null);
  const [characters, setCharacters] = useState<WorkflowCharacterList | null>(null);
  const [library, setLibrary] = useState<WorkflowLibrary | null>(null);
  const [productionStatus, setProductionStatus] = useState<WorkflowProductionStatus | null>(null);
  const [creditSummary, setCreditSummary] = useState<CreditBalance | null>(null);
  const [productionEstimate, setProductionEstimate] = useState<number>(20);
  const [socialConnections, setSocialConnections] = useState<SocialAccountConnection[]>([]);
  const [publishQueue, setPublishQueue] = useState<SocialPublishJob[]>([]);
  const [publishStatus, setPublishStatus] = useState<string | null>(null);
  const [socialStatus, setSocialStatus] = useState<string | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [socialError, setSocialError] = useState<string | null>(null);
  const [socialConnectionId, setSocialConnectionId] = useState<string | null>(null);
  const [socialPlatform, setSocialPlatform] = useState<SocialAccountConnection["platform"]>("youtube");
  const [socialSettingsOpenPlatform, setSocialSettingsOpenPlatform] = useState<SocialAccountConnection["platform"] | null>(null);
  const [socialAccountLabel, setSocialAccountLabel] = useState("");
  const [socialAccountIdentifier, setSocialAccountIdentifier] = useState("");
  const [socialSaving, setSocialSaving] = useState(false);
  const [socialPublishingId, setSocialPublishingId] = useState<string | null>(null);
  const [publishCaption, setPublishCaption] = useState("");
  const [publishSendMode, setPublishSendMode] = useState<"single" | "bulk">("single");
  const [showCreditPanel, setShowCreditPanel] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [creditPlans, setCreditPlans] = useState<CreditPlan[]>([]);
  const [creditPlansLoading, setCreditPlansLoading] = useState(false);
  const [creditPlansError, setCreditPlansError] = useState<string | null>(null);
  const [billingReceipts, setBillingReceipts] = useState<BillingReceipt[]>([]);
  const [billingReceiptsLoading, setBillingReceiptsLoading] = useState(false);
  const [billingReceiptsError, setBillingReceiptsError] = useState<string | null>(null);
  const [billingReceiptsMessage, setBillingReceiptsMessage] = useState<string | null>(null);
  const [billingReceiptDeleteId, setBillingReceiptDeleteId] = useState<number | null>(null);
  const [transactionRecords, setTransactionRecords] = useState<BillingTransactionRecord[]>([]);
  const [transactionRecordsLoading, setTransactionRecordsLoading] = useState(false);
  const [transactionRecordsError, setTransactionRecordsError] = useState<string | null>(null);
  const [transactionRecordsMessage, setTransactionRecordsMessage] = useState<string | null>(null);
  const [purchaseLoadingPlan, setPurchaseLoadingPlan] = useState<string | null>(null);
  const [purchaseStatus, setPurchaseStatus] = useState<string | null>(null);
  const [selectedCreditPlanId, setSelectedCreditPlanId] = useState<string | null>(null);
  const [selectedPurchaseProvider, setSelectedPurchaseProvider] = useState<BillingProvider>("stripe");
  const [feedbackSubject, setFeedbackSubject] = useState("Feature suggestion");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [communityPosts, setCommunityPosts] = useState<CommunityPost[]>([]);
  const [communityLoading, setCommunityLoading] = useState(false);
  const [communitySending, setCommunitySending] = useState(false);
  const [communityReactingPostId, setCommunityReactingPostId] = useState<string | null>(null);
  const [communitySubject, setCommunitySubject] = useState("Feature idea");
  const [communityMessage, setCommunityMessage] = useState("");
  const [communityStatus, setCommunityStatus] = useState<string | null>(null);
  const [communityError, setCommunityError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [titleInput, setTitleInput] = useState("");
  const [autoCreateTitle, setAutoCreateTitle] = useState("");
  const [autoCreateShortDescription, setAutoCreateShortDescription] = useState("");
  const [autoCreateGenre, setAutoCreateGenre] = useState("Adventure");
  const [autoCreateDuration, setAutoCreateDuration] = useState(10);
  const [autoCreateStartCredits, setAutoCreateStartCredits] = useState("");
  const [autoCreateEndCredits, setAutoCreateEndCredits] = useState("");
  const [autoCreateCustomCharacters, setAutoCreateCustomCharacters] = useState<AutoCreateCharacterDraft[]>([]);
  const [autoCreateCharacterPanelOpen, setAutoCreateCharacterPanelOpen] = useState(false);
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
  const [lockCharacterIdentity, setLockCharacterIdentity] = useState(true);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [libraryCharacterName, setLibraryCharacterName] = useState("");
  const [libraryCharacterRole, setLibraryCharacterRole] = useState("supporting");
  const [libraryCharacterDescription, setLibraryCharacterDescription] = useState("");
  const [libraryCharacterTraits, setLibraryCharacterTraits] = useState("");
  const [libraryCharacterVoice, setLibraryCharacterVoice] = useState("default");
  const [libraryLockCharacterIdentity, setLibraryLockCharacterIdentity] = useState(true);
  const [libraryUploadFile, setLibraryUploadFile] = useState<File | null>(null);
  const [productionConfirmed, setProductionConfirmed] = useState(false);
  const [characterSearch, setCharacterSearch] = useState("");
  const [characterRoleFilter, setCharacterRoleFilter] = useState<CharacterRoleFilter>("all");
  const [publishProjectId, setPublishProjectId] = useState<string | null>(null);
  const [factoryModeTitleQueue, setFactoryModeTitleQueue] = useState(
    "Launch title one\nLaunch title two"
  );
  const [factoryModeRunnerStatus, setFactoryModeRunnerStatus] = useState<OrchestrationRunnerStatus | null>(null);
  const [factoryModeMessage, setFactoryModeMessage] = useState<string | null>(null);
  const [factoryModeError, setFactoryModeError] = useState<string | null>(null);
  const [playVideoControlsVisible, setPlayVideoControlsVisible] = useState(true);
  const [isPlayFullscreen, setIsPlayFullscreen] = useState(false);
  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
  const creditBalance = creditSummary?.credits_balance ?? null;
  const creditUsedTotal = creditSummary?.credits_used_total ?? null;
  const creditTotal = creditBalance !== null && creditUsedTotal !== null ? creditBalance + creditUsedTotal : null;
  const characterSlotSummary = creditSummary?.character_slots ?? null;
  const ownerModeEnabled = Boolean(creditSummary?.owner_mode_enabled);
  const characterLibraryFull = Boolean(characterSlotSummary?.is_full);
  const factoryModeDeploymentEnabled = FACTORY_MODE_ENABLED || ownerModeEnabled;
  const factoryModeActivated = factoryModeAccessIsActive(
    creditSummary ? { ...creditSummary, owner_mode_enabled: ownerModeEnabled } : creditSummary
  );
  const appShellRef = useRef<HTMLDivElement | null>(null);
  const storyRequestRef = useRef<HTMLDivElement | null>(null);
  const scriptReviewRef = useRef<HTMLDivElement | null>(null);
  const charactersRef = useRef<HTMLDivElement | null>(null);
  const productionRef = useRef<HTMLDivElement | null>(null);
  const playControlsHideTimerRef = useRef<number | null>(null);
  const paymentStepRef = useRef<HTMLDivElement | null>(null);
  const purchaseProviderManuallyChosenRef = useRef(false);
  const lastProjectWorkflowStateRef = useRef<WorkflowState | null>(null);

  const selectedStage = workflowStageIndex(selectedProject);
  const activeProject = selectedProject ?? projects[0] ?? null;
  const playbackMode = activeNav === "play";
  const guidance = createGuidance(selectedProject, productionStatus, productionConfirmed);
  const workflowWarnings = createWorkflowWarnings(selectedProject);
  const storyStatus = stepOneStatus(selectedProject, busy);
  const scriptStatus = stepTwoStatus(selectedProject, busy);
  const characterStatus = stepThreeStatus(selectedProject, characters, busy);
  const productionStepStatus = stepFourStatus(selectedProject, productionStatus, productionConfirmed, busy);
  const autoCreateAvailableDuration = 120;
  const isAutoCreateGenreFactual = autoCreateGenre === "True Story" || autoCreateGenre === "Real Events";
  const isAutoCreateRealEvents = autoCreateGenre === "Real Events";

  const approvedScripts = useMemo(
    () => (library?.scripts ?? projects.filter((project) => Boolean((project.script_approved || "").trim()))),
    [library, projects]
  );
  const completedVideos = useMemo(
    () => (library?.videos ?? projects.filter((project) => Boolean((project.final_video_url || "").trim()))),
    [library, projects]
  );
  const creditPurchasePlans = useMemo(
    () => creditPlans.filter((plan) => !isFactoryAccessPlan(plan)),
    [creditPlans]
  );
  const factoryAccessPlans = useMemo(
    () => creditPlans.filter((plan) => isFactoryAccessPlan(plan)),
    [creditPlans]
  );
  const factoryModeQueueTitles = useMemo(
    () =>
      factoryModeTitleQueue
        .split(/\r?\n/)
        .map((title) => title.trim())
        .filter(Boolean),
    [factoryModeTitleQueue]
  );
  const selectedCreditPlan = useMemo(
    () => creditPlans.find((plan) => plan.id === selectedCreditPlanId) ?? null,
    [creditPlans, selectedCreditPlanId]
  );
  const selectedCreditPlanProviders = useMemo(
    () => (selectedCreditPlan ? checkoutProvidersForPlan(selectedCreditPlan) : []),
    [selectedCreditPlan]
  );
  const purchaseProviderOptions = useMemo(() => {
    if (!selectedCreditPlan) {
      return [];
    }
    return selectedCreditPlanProviders.length > 0 ? selectedCreditPlanProviders : (["paystack", "stripe"] as BillingProvider[]);
  }, [selectedCreditPlan, selectedCreditPlanProviders]);
  const preferredPurchaseProvider = useMemo(
    () => inferPreferredBillingProvider(purchaseProviderOptions) ?? detectBrowserPreferredBillingProvider(),
    [purchaseProviderOptions]
  );
  const handleAutoCreateGenreChange = useCallback(
    (nextGenre: string) => {
      setAutoCreateGenre(nextGenre);
      if (nextGenre === "Real Events") {
        setAutoCreateCustomCharacters([]);
      }
      if (nextGenre === "Series Video Maker (Factory Mode Only)") {
        router.push("/factory-mode");
      }
    },
    [router]
  );
  const downloadProject = useMemo(() => {
    return (
      completedVideos.find((project) => project.project_id === publishProjectId) ??
      (selectedProject?.final_video_url ? selectedProject : null) ??
      completedVideos[0] ??
      null
    );
  }, [completedVideos, publishProjectId, selectedProject]);
  const publishProject = useMemo(() => {
    return (
      completedVideos.find((project) => project.project_id === publishProjectId) ??
      (selectedProject?.final_video_url ? selectedProject : null) ??
      completedVideos[0] ??
      null
    );
  }, [completedVideos, publishProjectId, selectedProject]);
  const visibleCharacterLibrary = useMemo(() => {
    const source = characters?.library ?? library?.characters ?? [];
    const query = characterSearch.trim().toLowerCase();
    return source.filter((character) => {
      if (!character.name.trim()) {
        return false;
      }
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
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  const syncPlayFullscreen = useCallback(() => {
    if (typeof document === "undefined") {
      return;
    }
    const fullscreenElement = document.fullscreenElement;
    setIsPlayFullscreen(Boolean(fullscreenElement && fullscreenElement === appShellRef.current));
  }, []);

  const enterPlayFullscreen = useCallback(async () => {
    const element = appShellRef.current;
    if (!element || typeof element.requestFullscreen !== "function") {
      return;
    }
    if (typeof document !== "undefined" && document.fullscreenElement === element) {
      return;
    }
    await element.requestFullscreen();
    syncPlayFullscreen();
  }, [syncPlayFullscreen]);

  const exitPlayFullscreen = useCallback(async () => {
    if (typeof document === "undefined" || typeof document.exitFullscreen !== "function") {
      return;
    }
    if (!document.fullscreenElement) {
      return;
    }
    await document.exitFullscreen();
    syncPlayFullscreen();
  }, [syncPlayFullscreen]);

  function handleNavSelect(next: NavItem) {
    if (next === "factory-mode") {
      router.push("/factory-mode");
      setMobileDrawerOpen(false);
      return;
    }
    setActiveNav(next);
    setMobileDrawerOpen(false);
    if (next === "play") {
      setPlayVideoControlsVisible(true);
      void enterPlayFullscreen();
    } else if (isPlayFullscreen) {
      void exitPlayFullscreen();
    }
  }

  useEffect(() => {
    const nav = searchParams?.get?.("nav") ?? null;
    if (nav === "factory-mode") {
      router.replace("/factory-mode");
      return;
    }
    if (nav && ALL_NAV_ITEMS.some((item) => item.id === nav)) {
      setActiveNav(nav as NavItem);
    } else {
      setActiveNav("auto-create");
    }
    const projectId = searchParams?.get?.("project") ?? null;
    if (projectId) {
      setPublishProjectId(projectId);
    }
    const creditsPanel = searchParams?.get?.("credits") ?? null;
    if (creditsPanel === "1" || creditsPanel === "true" || creditsPanel === "plans") {
      setShowCreditPanel(true);
    }
  }, [router, searchParams]);

  useEffect(() => {
    if (activeNav !== "create" || !selectedProject) {
      return;
    }
    scrollToCreateStep(selectedStage);
  }, [activeNav, selectedProject, selectedStage]);

  const refreshProjects = useCallback(async (nextSelectedId?: string | null) => {
    const [workflowProjects, credits, workflowLibrary] = await Promise.all([
      fetchWorkflowProjects(),
      fetchMyCredits().catch(() => null),
      fetchWorkflowLibrary().catch(() => null),
    ]);
    setProjects(workflowProjects);
    setCreditSummary(credits);
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
  }, [selectedProjectId]);

  const refreshProject = useCallback(async (projectId: string) => {
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
      setCreditSummary((current) =>
        current
          ? { ...current, credits_balance: summary.current_credit_balance }
          : current
      );
    }
  }, []);

  const refreshSocialState = useCallback(async (projectId?: string | null) => {
    setSocialLoading(true);
    try {
      const [connections, jobs] = await Promise.all([
        fetchSocialConnections().catch(() => ({ items: [] })),
        projectId
          ? fetchSocialPublishJobs({ project_id: projectId }).catch(() => ({ items: [] }))
          : Promise.resolve({ items: [] }),
      ]);
      const nextConnections = connections.items ?? [];
      setSocialConnections(nextConnections);
      setPublishQueue(jobs.items ?? []);
      setSocialConnectionId((current) =>
        current && nextConnections.some((connection) => connection.connection_id === current)
          ? current
          : nextConnections[0]?.connection_id ?? null
      );
    } finally {
      setSocialLoading(false);
    }
  }, []);

  const refreshCommunityPosts = useCallback(async () => {
    setCommunityLoading(true);
    setCommunityError(null);
    try {
      const response = await fetchCommunityPosts();
      setCommunityPosts(response.items ?? []);
    } catch (err) {
      setCommunityError(err instanceof Error ? err.message : "Failed to load community posts");
    } finally {
      setCommunityLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const syncAuthState = () => setIsAuthenticated(Boolean(window.localStorage.getItem("pc_token")));
    syncAuthState();
    window.addEventListener("storage", syncAuthState);
    return () => window.removeEventListener("storage", syncAuthState);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const openSubscription = () => {
      setShowCreditPanel(true);
      setCreditPlansError(null);
      setPurchaseStatus(null);
    };
    window.addEventListener("procreator:subscription-required", openSubscription);
    return () => window.removeEventListener("procreator:subscription-required", openSubscription);
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      if (!isAuthenticated) {
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await withTimeout(refreshProjects(), WORKFLOW_LOAD_TIMEOUT_MS, "Workflow load");
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
  }, [isAuthenticated, refreshProjects]);

  useEffect(() => {
    if (!isAuthenticated || !selectedProjectId) {
      return;
    }
    let active = true;
    const loadProject = async () => {
      try {
        await withTimeout(refreshProject(selectedProjectId), WORKFLOW_LOAD_TIMEOUT_MS, "Project load");
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
  }, [isAuthenticated, refreshProject, selectedProjectId]);

  useEffect(() => {
    setProductionConfirmed(false);
  }, [selectedProject?.project_id, selectedProject?.script_approved_at, selectedProject?.character_package_approved_at]);

  useEffect(() => {
    const nextState = selectedProject?.workflow_state ?? null;
    const previousState = lastProjectWorkflowStateRef.current;
    if (nextState === "video_completed" && previousState !== "video_completed") {
      setStatus(VIDEO_READY_MESSAGE);
    }
    lastProjectWorkflowStateRef.current = nextState;
  }, [selectedProject?.project_id, selectedProject?.workflow_state]);

  useEffect(() => {
    if (!isAuthenticated || activeNav !== "publish" || !publishProject?.project_id) {
      return;
    }
    void refreshSocialState(publishProject.project_id);
  }, [activeNav, isAuthenticated, publishProject?.project_id, refreshSocialState]);

  useEffect(() => {
    if (!isAuthenticated || activeNav !== "community") {
      return;
    }
    void refreshCommunityPosts();
  }, [activeNav, isAuthenticated, refreshCommunityPosts]);

  useEffect(() => {
    if (!publishProject?.project_id || publishCaption.trim()) {
      return;
    }
    setPublishCaption(publishProject.title || "");
  }, [publishCaption, publishProject?.project_id, publishProject?.title]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    syncPlayFullscreen();
    document.addEventListener("fullscreenchange", syncPlayFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncPlayFullscreen);
  }, [syncPlayFullscreen]);

  useEffect(() => {
    if (playControlsHideTimerRef.current) {
      window.clearTimeout(playControlsHideTimerRef.current);
      playControlsHideTimerRef.current = null;
    }
    if (!playbackMode) {
      setPlayVideoControlsVisible(true);
      return;
    }

    const showControls = () => {
      setPlayVideoControlsVisible(true);
      if (playControlsHideTimerRef.current) {
        window.clearTimeout(playControlsHideTimerRef.current);
      }
      playControlsHideTimerRef.current = window.setTimeout(() => {
        setPlayVideoControlsVisible(false);
      }, 2200);
    };

    showControls();

    const events: Array<keyof WindowEventMap> = ["mousemove", "mousedown", "keydown", "touchstart", "focusin"];
    events.forEach((eventName) => window.addEventListener(eventName, showControls));
    return () => {
      events.forEach((eventName) => window.removeEventListener(eventName, showControls));
      if (playControlsHideTimerRef.current) {
        window.clearTimeout(playControlsHideTimerRef.current);
        playControlsHideTimerRef.current = null;
      }
    };
  }, [playbackMode]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      const isAccel = event.metaKey || event.ctrlKey;
      if (!isAccel || !event.shiftKey || !event.altKey) {
        return;
      }
      if (event.code !== "KeyA") {
        return;
      }
      event.preventDefault();
      window.location.href = "/admin";
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!showCreditPanel || creditPlans.length > 0) {
      return;
    }
    let active = true;
    const loadPlans = async () => {
      setCreditPlansLoading(true);
      setCreditPlansError(null);
      try {
        const response = await fetchCreditPlans();
        if (active) {
          setCreditPlans(response.plans ?? []);
        }
      } catch (err) {
        if (active) {
          setCreditPlansError(err instanceof Error ? err.message : "Failed to load credit plans");
        }
      } finally {
        if (active) {
          setCreditPlansLoading(false);
        }
      }
    };
    void loadPlans();
    return () => {
      active = false;
    };
  }, [creditPlans.length, showCreditPanel]);

  useEffect(() => {
    if (!showCreditPanel || !isAuthenticated) {
      setBillingReceipts([]);
      setBillingReceiptsError(null);
      setBillingReceiptsLoading(false);
      return;
    }
    let active = true;
    const loadReceipts = async () => {
      setBillingReceiptsLoading(true);
      setBillingReceiptsError(null);
      try {
        const response = await fetchBillingReceipts();
        if (active) {
          setBillingReceipts(response.items ?? []);
        }
      } catch (err) {
        if (active) {
          setBillingReceiptsError(err instanceof Error ? err.message : "Failed to load receipts");
        }
      } finally {
        if (active) {
          setBillingReceiptsLoading(false);
        }
      }
    };
    void loadReceipts();
    return () => {
      active = false;
    };
  }, [isAuthenticated, showCreditPanel]);

  useEffect(() => {
    if (!isAuthenticated || activeNav !== "transaction-records") {
      return;
    }
    let active = true;
    const loadTransactionRecords = async () => {
      setTransactionRecordsLoading(true);
      setTransactionRecordsError(null);
      setTransactionRecordsMessage(null);
      try {
        const response = await fetchBillingTransactionRecords();
        if (active) {
          setTransactionRecords(response.items ?? []);
        }
      } catch (err) {
        if (active) {
          setTransactionRecordsError(err instanceof Error ? err.message : "Failed to load transaction records");
        }
      } finally {
        if (active) {
          setTransactionRecordsLoading(false);
        }
      }
    };
    void loadTransactionRecords();
    return () => {
      active = false;
    };
  }, [activeNav, isAuthenticated]);

  const handleDeleteReceipt = useCallback(async (receiptId: number) => {
    setBillingReceiptDeleteId(receiptId);
    setBillingReceiptsError(null);
    setBillingReceiptsMessage(null);
    try {
      const deletion = await deleteBillingReceipt(receiptId);
      setBillingReceipts((items) => items.filter((receipt) => receipt.receipt_id !== receiptId));
      try {
        const refreshed = await fetchBillingReceipts();
        setBillingReceipts(refreshed.items ?? []);
      } catch {
        // Keep the optimistic update if the refresh fails.
      }
      setBillingReceiptsMessage(
        deletion.deleted_permanently ? "Receipt deleted permanently." : "Receipt removed from your view."
      );
    } catch (err) {
      setBillingReceiptsError(err instanceof Error ? err.message : "Failed to delete receipt");
    } finally {
      setBillingReceiptDeleteId(null);
    }
  }, []);

  useEffect(() => {
    if (activeNav !== "factory-mode") {
      return;
    }
    let active = true;
    const loadRunnerStatus = async () => {
      try {
        const runner = await fetchOrchestrationRunnerStatus();
        if (active) {
          setFactoryModeRunnerStatus(runner);
        }
      } catch {
        if (active) {
          setFactoryModeRunnerStatus(null);
        }
      }
    };
    void loadRunnerStatus();
    return () => {
      active = false;
    };
  }, [activeNav]);

  useEffect(() => {
    if (!showCreditPanel || creditPlans.length === 0 || selectedCreditPlanId) {
      return;
    }
    const defaultPlan =
      creditPurchasePlans.find((plan) => plan.popular && plan.checkout_enabled) ??
      creditPurchasePlans.find((plan) => plan.checkout_enabled) ??
      creditPurchasePlans[0] ??
      factoryAccessPlans.find((plan) => plan.checkout_enabled) ??
      factoryAccessPlans[0] ??
      creditPlans[0];
    setSelectedCreditPlanId(defaultPlan?.id ?? null);
  }, [creditPlans, creditPurchasePlans, factoryAccessPlans, selectedCreditPlanId, showCreditPanel]);

  useEffect(() => {
    if (!showCreditPanel || purchaseProviderOptions.length === 0) {
      return;
    }
    const fallbackProvider = preferredPurchaseProvider ?? purchaseProviderOptions[0];
    if (!fallbackProvider) {
      return;
    }
    if (purchaseProviderManuallyChosenRef.current) {
      if (!purchaseProviderOptions.includes(selectedPurchaseProvider)) {
        setSelectedPurchaseProvider(fallbackProvider);
      }
      return;
    }
    if (selectedPurchaseProvider !== fallbackProvider) {
      setSelectedPurchaseProvider(fallbackProvider);
    }
  }, [preferredPurchaseProvider, purchaseProviderOptions, selectedPurchaseProvider, showCreditPanel]);

  useEffect(() => {
    if (!showCreditPanel || !selectedCreditPlan) {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const target = paymentStepRef.current;
      if (target && typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selectedCreditPlanId, showCreditPanel, selectedCreditPlan]);

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
  }, [refreshProject, refreshProjects, selectedProject, selectedProjectId]);

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

  async function handleDeleteAllProjects(nextNav: NavItem = "projects") {
    setBusy("delete-projects");
    setError(null);
    setStatus(null);
    try {
      await deleteWorkflowProjects();
      await refreshProjects(null);
      setSelectedProject(null);
      setCharacters(null);
      setProductionStatus(null);
      setTitleInput("");
      setIdeaInput("");
      setGenreInput("");
      setDurationInput(3);
      setScriptInput("");
      setProductionConfirmed(false);
      setActiveNav(nextNav);
      setStatus(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete projects");
    } finally {
      setBusy(null);
    }
  }

  function handleAddAutoCreateCharacterRow() {
    setAutoCreateCustomCharacters((current) =>
      current.length >= AUTO_CREATE_MAX_CUSTOM_CHARACTERS
        ? current
        : [...current, createAutoCreateCharacterDraft()]
    );
  }

  function handleUpdateAutoCreateCharacterRow(
    rowId: string,
    field: keyof Omit<AutoCreateCharacterDraft, "id">,
    value: string
  ) {
    setAutoCreateCustomCharacters((current) =>
      current.map((row) => (row.id === rowId ? { ...row, [field]: value } : row))
    );
  }

  function handleRemoveAutoCreateCharacterRow(rowId: string) {
    setAutoCreateCustomCharacters((current) => current.filter((row) => row.id !== rowId));
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

  async function handleAutoCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTitle = autoCreateTitle.trim();
    if (!cleanTitle) {
      setError("Add a video title first.");
      return;
    }
    const customCharacters = autoCreateCustomCharacters
      .map((character) => ({
        name: character.name.trim(),
        role_type: character.role_type.trim(),
        description: character.description.trim(),
      }))
      .filter((character) => character.name || character.role_type || character.description);
    if (customCharacters.length > 0) {
      const invalidCharacter = customCharacters.find((character) => !character.name || !character.role_type);
      if (invalidCharacter) {
        setError("Each custom character needs a name and role.");
        return;
      }
    }
    if (autoCreateGenre === "Real Events" && customCharacters.length > 0) {
      setError("Real Events does not use character generation.");
      return;
    }
    setBusy("auto-create");
    setError(null);
    setStatus(null);
    try {
      const response = await autoCreateWorkflowProject({
        title: cleanTitle,
        duration_minutes: autoCreateDuration,
        genre: autoCreateGenre,
        short_description: autoCreateShortDescription.trim() || undefined,
        start_credits: autoCreateStartCredits.trim() || undefined,
        end_credits: autoCreateEndCredits.trim() || undefined,
        custom_characters: customCharacters,
      });
      setSelectedProjectId(response.project.project_id);
      setPublishProjectId(response.project.project_id);
      await refreshProjects(response.project.project_id);
      await refreshProject(response.project.project_id);
      setAutoCreateTitle("");
      setAutoCreateShortDescription("");
      setAutoCreateGenre("Adventure");
      setAutoCreateDuration(10);
      setAutoCreateStartCredits("");
      setAutoCreateEndCredits("");
      setAutoCreateCustomCharacters([]);
      setStatus(VIDEO_READY_MESSAGE);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to auto-create project");
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

  async function handleLibraryCharacterAction(mode: "manual" | "generate" | "upload") {
    setBusy(`library-character-${mode}`);
    setError(null);
    setStatus(null);
    try {
      const cleanName = libraryCharacterName.trim();
      const cleanDescription = libraryCharacterDescription.trim();
      if (!cleanName) {
        throw new Error("Add a character name before continuing.");
      }
      if (!cleanDescription) {
        throw new Error("Add a short character description before continuing.");
      }
      const traits = libraryCharacterTraits
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      let nextLibrary: WorkflowLibrary;
      if (mode === "generate") {
        nextLibrary = await generateLibraryCharacter({
          name: cleanName,
          role_type: libraryCharacterRole,
          description: cleanDescription,
          personality_traits: traits,
          voice_profile: libraryCharacterVoice,
          style: "cinematic",
          lock_identity: libraryLockCharacterIdentity,
        });
      } else if (mode === "upload") {
        if (!libraryUploadFile) {
          throw new Error("Choose a reference image before uploading");
        }
        nextLibrary = await uploadLibraryCharacter({
          file: libraryUploadFile,
          name: cleanName,
          role_type: libraryCharacterRole,
          description: cleanDescription,
          voice_profile: libraryCharacterVoice,
          lock_identity: libraryLockCharacterIdentity,
        });
      } else {
        nextLibrary = await createLibraryCharacter({
          name: cleanName,
          role_type: libraryCharacterRole,
          description: cleanDescription,
          personality_traits: traits,
          voice_profile: libraryCharacterVoice,
          lock_identity: libraryLockCharacterIdentity,
        });
      }
      setLibrary(nextLibrary);
      setCharacters((current) =>
        current ? { ...current, library: nextLibrary.characters ?? [] } : current
      );
      setLibraryCharacterName("");
      setLibraryCharacterDescription("");
      setLibraryCharacterTraits("");
      setLibraryCharacterVoice("default");
      setLibraryLockCharacterIdentity(true);
      setLibraryUploadFile(null);
      setStatus("Character saved to the library.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save library character");
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

  async function handlePurchaseCharacterSlots() {
    setBusy("purchase-character-slots");
    setError(null);
    setStatus(null);
    try {
      const updatedCredits = await purchaseCharacterSlotPack({ pack_count: 1 });
      setCreditSummary(updatedCredits);
      setStatus(
        `Character library expanded by ${updatedCredits.character_slots.addon_pack_size} slots.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to buy more character slots");
    } finally {
      setBusy(null);
    }
  }

  async function handlePurchasePlan(planId: string) {
    if (!isAuthenticated) {
      router.push("/login?mode=register&next=%2F%3Fcredits%3D1");
      return;
    }
    setPurchaseLoadingPlan(planId);
    setPurchaseStatus(null);
    try {
      const checkout = await createStripeCheckoutSession({
        plan_id: planId,
        provider: selectedPurchaseProvider,
      });
      if (typeof window !== "undefined" && process.env.NODE_ENV !== "test") {
        window.location.href = checkout.checkout_url;
      }
    } catch (err) {
      setPurchaseStatus(err instanceof Error ? err.message : "Purchase failed");
    } finally {
      setPurchaseLoadingPlan(null);
    }
  }

  function handleOpenCreditPanel() {
    setShowCreditPanel(true);
    setCreditPlansError(null);
    setPurchaseStatus(null);
    setBillingReceiptsMessage(null);
  }

  function handleCloseCreditPanel() {
    setShowCreditPanel(false);
  }

  function handleSelectCreditPlan(planId: string) {
    setSelectedCreditPlanId(planId);
    setPurchaseStatus(null);
  }

  function handleSelectPurchaseProvider(provider: BillingProvider) {
    purchaseProviderManuallyChosenRef.current = true;
    setSelectedPurchaseProvider(provider);
  }

  async function handleStartFactoryMode() {
    if (!factoryModeActivated) {
      return;
    }
    if (factoryModeQueueTitles.length === 0) {
      setFactoryModeError("Add at least one title to the factory queue.");
      setFactoryModeMessage(null);
      return;
    }
    setBusy("factory-mode-start");
    setFactoryModeError(null);
    setFactoryModeMessage(null);
    try {
      const queueItem = await enqueueOrchestrationJob({
        project_id: "factory-mode",
        kind: "factory_mode",
        titles: factoryModeQueueTitles,
        duration_minutes: autoCreateDuration,
        genre: autoCreateGenre,
        short_description: autoCreateShortDescription.trim() || undefined,
        start_credits: autoCreateStartCredits.trim() || undefined,
        end_credits: autoCreateEndCredits.trim() || undefined,
        publish_message: autoCreateTitle.trim() || factoryModeQueueTitles[0],
      });
      try {
        const runner = await startOrchestrationRunner({ interval_seconds: 5 });
        setFactoryModeRunnerStatus(runner);
      } catch {
        // Queue may be worker-managed in deployed environments.
      }
      setFactoryModeMessage(`Queued ${factoryModeQueueTitles.length} title${factoryModeQueueTitles.length === 1 ? "" : "s"}.`);
      setFactoryModeRunnerStatus((current) => current ?? { enabled: true, running: true, interval_seconds: 5, detail: null });
      setStatus(`Factory Mode job ${queueItem.id} queued.`);
    } catch (err) {
      setFactoryModeError(err instanceof Error ? err.message : "Failed to start Factory Mode");
    } finally {
      setBusy(null);
    }
  }

  async function handleStopFactoryMode() {
    if (!factoryModeDeploymentEnabled) {
      return;
    }
    setBusy("factory-mode-stop");
    setFactoryModeError(null);
    try {
      const runner = await stopOrchestrationRunner();
      setFactoryModeRunnerStatus(runner);
      setFactoryModeMessage("Factory runner paused.");
      setStatus("Factory Mode runner stopped.");
    } catch (err) {
      setFactoryModeError(err instanceof Error ? err.message : "Failed to stop Factory Mode");
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

  async function handleSaveSocialConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSocialSaving(true);
    setSocialError(null);
    setPublishStatus(null);
    try {
      if (!socialAccountLabel.trim()) {
        throw new Error("Add a label for this account.");
      }
      const response = await saveSocialConnection({
        connection_id: socialConnectionId,
        platform: socialPlatform,
        account_label: socialAccountLabel,
        account_identifier: socialAccountIdentifier || null,
        scopes: [],
        metadata: {},
        enabled: true,
      });
      setSocialConnectionId(null);
      setSocialAccountLabel("");
      setSocialAccountIdentifier("");
      await refreshSocialState(publishProject?.project_id);
      setSocialStatus(`Saved ${response.account_label} on ${response.platform}.`);
    } catch (err) {
      setSocialError(err instanceof Error ? err.message : "Failed to save social connection");
    } finally {
      setSocialSaving(false);
    }
  }

  async function handleDeleteSocialAccount(connectionId: string) {
    setBusy(`social-delete-${connectionId}`);
    setSocialError(null);
    setPublishStatus(null);
    try {
      await deleteSocialConnection(connectionId);
      await refreshSocialState(publishProject?.project_id);
      setSocialStatus("Social account removed.");
    } catch (err) {
      setSocialError(err instanceof Error ? err.message : "Failed to delete social connection");
    } finally {
      setBusy(null);
    }
  }

  async function handlePublishConnection(connectionId: string) {
    if (!publishProject?.project_id) {
      setSocialError("Select a finished project first.");
      return;
    }
    setSocialPublishingId(connectionId);
    setSocialError(null);
    setPublishStatus(null);
    try {
      const response = await publishSocialVideos({
        project_id: publishProject.project_id,
        connection_ids: [connectionId],
        message: publishCaption || publishProject.title,
        title: publishProject.title,
      });
      const last = response.items[response.items.length - 1];
      setPublishStatus(
        last?.published_url
          ? `Published to ${last.platform}: ${last.published_url}`
          : `Publish job completed for ${last?.platform ?? "selected account"}.`
      );
      await refreshSocialState(publishProject.project_id);
      setCreditSummary(await fetchMyCredits().catch(() => null));
    } catch (err) {
      setSocialError(err instanceof Error ? err.message : "Failed to publish to the selected account");
    } finally {
      setSocialPublishingId(null);
    }
  }

  async function handlePublishAllConnected() {
    if (!publishProject?.project_id) {
      setSocialError("Select a finished project first.");
      return;
    }
    setBusy("social-publish-all");
    setSocialError(null);
    setPublishStatus(null);
    try {
      const response = await publishSocialVideos({
        project_id: publishProject.project_id,
        message: publishCaption || publishProject.title,
        title: publishProject.title,
      });
      setPublishStatus(`Published to ${response.items.length} connected account(s).`);
      await refreshSocialState(publishProject.project_id);
      setCreditSummary(await fetchMyCredits().catch(() => null));
    } catch (err) {
      setSocialError(err instanceof Error ? err.message : "Failed to publish to connected accounts");
    } finally {
      setBusy(null);
    }
  }

  async function handleSubmitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedbackSending(true);
    setFeedbackError(null);
    setFeedbackStatus(null);
    try {
      const subject = feedbackSubject.trim();
      const message = feedbackMessage.trim();
      if (!subject) {
        throw new Error("Add a subject for your feedback.");
      }
      if (!message) {
        throw new Error("Write your feedback message before sending.");
      }
      const response = await submitWorkflowFeedback({
        subject,
        message,
        page: activeNav,
        project_id: (selectedProject ?? activeProject)?.project_id ?? null,
      });
      setFeedbackStatus(
        response.email_sent
          ? "Feedback sent."
          : "Feedback saved. Email delivery is not configured yet."
      );
      setFeedbackMessage("");
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : "Failed to send feedback");
    } finally {
      setFeedbackSending(false);
    }
  }

  async function handleSubmitCommunityPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCommunitySending(true);
    setCommunityError(null);
    setCommunityStatus(null);
    try {
      const subject = communitySubject.trim();
      const message = communityMessage.trim();
      if (!subject) {
        throw new Error("Add a subject for the community post.");
      }
      if (!message) {
        throw new Error("Write a message before posting.");
      }
      await createCommunityPost({ subject, message });
      setCommunityStatus("Posted to X'treamers.");
      setCommunityMessage("");
      await refreshCommunityPosts();
    } catch (err) {
      setCommunityError(err instanceof Error ? err.message : "Failed to post to the community");
    } finally {
      setCommunitySending(false);
    }
  }

  async function handleApplaudCommunityPost(postId: string) {
    setCommunityReactingPostId(postId);
    setCommunityError(null);
    try {
      await applaudCommunityPost(postId);
      await refreshCommunityPosts();
    } catch (err) {
      setCommunityError(err instanceof Error ? err.message : "Failed to react to the community post");
    } finally {
      setCommunityReactingPostId(null);
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

  function renderWorkflowProgress() {
    const progressProject = selectedProject;
    if (!progressProject) {
      return null;
    }
    const progress = workflowProgressPercent(progressProject);
    const copy = workflowProgressCopy(progressProject);
    const barClass =
      copy.tone === "success"
        ? "bg-emerald-400"
        : copy.tone === "warning"
          ? "bg-amber-400"
          : copy.tone === "danger"
            ? "bg-red-400"
            : "bg-aurora";
    return (
      <section className={`rounded-3xl border p-4 sm:p-5 ${guidanceClasses(copy.tone)}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.35em] opacity-70">
              Workflow progress
            </p>
            <h3 className="mt-2 text-lg font-semibold text-white">{copy.label}</h3>
          </div>
          <span className="rounded-full border border-white/10 bg-slate-950/35 px-3 py-1 text-xs font-semibold text-white">
            {progress}%
          </span>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-950/45">
          <div
            className={`h-full rounded-full transition-all duration-300 ${barClass}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-3 text-sm text-slate-100/90">{copy.detail}</p>
      </section>
    );
  }

  function renderFeedback() {
    return (
      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <h2 className="text-2xl font-semibold text-white">User Feedback</h2>

          {feedbackError ? (
            <p className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              {feedbackError}
            </p>
          ) : null}
          {feedbackStatus ? (
            <p className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              {feedbackStatus}
            </p>
          ) : null}

          <form className="mt-5 space-y-4" onSubmit={handleSubmitFeedback}>
            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Subject</span>
              <input
                className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                value={feedbackSubject}
                onChange={(event) => setFeedbackSubject(event.target.value)}
                placeholder="Feature idea"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Message</span>
              <textarea
                className="min-h-[140px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                value={feedbackMessage}
                onChange={(event) => setFeedbackMessage(event.target.value)}
                placeholder="Tell us what to improve."
              />
            </label>

            <button
              className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
              type="submit"
              disabled={feedbackSending}
            >
              {feedbackSending ? "Sending..." : "Submit"}
            </button>
          </form>
        </div>
      </section>
    );
  }

  function renderTransactionRecords() {
    return (
      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Transaction Records</p>
              <h2 className="mt-2 text-2xl font-semibold text-white">Immutable ledger copy</h2>
              <p className="mt-2 text-sm text-slate-400">Permanent credit history.</p>
            </div>
          </div>

          {transactionRecordsError ? (
            <p className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              {transactionRecordsError}
            </p>
          ) : null}
          {transactionRecordsMessage ? (
            <p className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              {transactionRecordsMessage}
            </p>
          ) : null}

          <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-white">Ledger entries</h3>
              <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Audit</span>
            </div>
            {transactionRecordsLoading ? (
              <p className="mt-3 text-sm text-slate-400">Loading transaction records...</p>
            ) : transactionRecords.length > 0 ? (
              <div className="mt-3 space-y-2">
                {transactionRecords.map((record) => {
                  const providerLabel =
                    record.provider === "paystack"
                      ? "Paystack / MoMo"
                      : record.provider === "stripe"
                        ? "Stripe"
                        : "Ledger";
                  const kindLabel = record.kind.replace(/_/g, " ");
                  return (
                    <div
                      key={record.record_id}
                      className="rounded-xl border border-slate-800 bg-slate-900/50 px-3 py-2 transition hover:border-slate-700 hover:bg-slate-900/70"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-[3px]">
                            <p className="text-sm font-semibold text-white capitalize">{kindLabel}</p>
                            <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                              {providerLabel}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-slate-400">{record.amount.toLocaleString()} credits</p>
                          {record.reason ? <p className="mt-1 text-xs text-slate-500">{record.reason}</p> : null}
                        </div>
                        <div className="flex flex-col items-end gap-2 text-right text-[10px] uppercase tracking-[0.18em] text-slate-500">
                          <p>{new Date(record.created_at).toLocaleString()}</p>
                          {record.reference_id ? (
                            <p className="font-mono text-slate-400 normal-case tracking-normal">
                              {record.reference_id}
                            </p>
                          ) : null}
                          <p className="text-slate-400">
                            Balance {record.balance_after} • Reserved {record.reserved_after}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">No records yet.</p>
            )}
          </div>
        </div>
      </section>
    );
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
                <div className="flex flex-wrap gap-3">
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
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Workflow</p>
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
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Credits</p>
              <p className="mt-3 text-3xl font-semibold text-white">
                {creditBalance ?? "—"}
              </p>
              <p className="mt-2 text-sm text-slate-500">
                {characterSlotSummary
                  ? `${characterSlotSummary.used_slots}/${characterSlotSummary.total_slots} slots`
                  : "—"}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-xl font-semibold text-white">Outputs</h2>
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
            <h2 className="mt-2 text-2xl font-semibold text-white">Projects</h2>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              className="rounded-full border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-semibold text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
              type="button"
              onClick={() => void handleDeleteAllProjects()}
              disabled={busy === "delete-projects" || projects.length === 0}
            >
              {busy === "delete-projects" ? "Deleting..." : "Delete all projects"}
            </button>
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
                <p>Step: {currentWorkflowStepLabel(project)}</p>
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
            <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400" />
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
            <h2 className="mt-2 text-2xl font-semibold text-white">Manual-Create</h2>
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
            </div>
            {selectedProject ? (
              <div className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-100">
                Step: {STEPS[selectedStage]}
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

        <div className="grid gap-4 xl:hidden">
          <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-500">
                  Quick Snapshot
                </p>
                <h3 className="mt-2 text-lg font-semibold text-white">
                  {selectedProject ? selectedProject.title : "New guided project"}
                </h3>
                <p className="mt-2 text-sm text-slate-400">
                  {selectedProject
                    ? selectedProject.idea_prompt || selectedProject.topic
                    : "Start with a title and short idea. The workflow unlocks each step after approval."}
                </p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs ${selectedProject ? statusPill(selectedProject.workflow_state) : "bg-slate-800 text-slate-400"}`}>
                {selectedProject ? workflowStageLabel(selectedProject.workflow_state) : "Draft"}
              </span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Step</p>
                <p className="mt-2 text-sm font-semibold text-white">{STEPS[selectedStage]}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Selected cast</p>
                <p className="mt-2 text-sm font-semibold text-white">{characters?.selected_character_ids.length ?? 0}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Credits and Slots</p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {creditBalance ?? "—"} credits
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {characterSlotSummary
                    ? `${characterSlotSummary.used_slots}/${characterSlotSummary.total_slots} characters used`
                    : "Character library usage unavailable"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Next</p>
                <p className="mt-2 text-sm font-semibold text-white">{nextUnlockCopy(selectedProject)}</p>
              </div>
            </div>
            {selectedProject ? (
              <button
                className="mt-5 rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                type="button"
                onClick={() => scrollToCreateStep(selectedStage)}
              >
                Jump
              </button>
            ) : null}
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.55fr]">
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Step</p>
                <p className="mt-2 text-sm font-semibold text-white">{STEPS[selectedStage]}</p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Script</p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {(selectedProject?.script_approved || "").trim() ? "Approved" : (selectedProject?.script_draft || "").trim() ? "Draft ready" : "Waiting"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cast</p>
                <p className="mt-2 text-sm font-semibold text-white">
                  {selectedProject?.character_package_approved ? "Approved" : `${characters?.selected_character_ids.length ?? 0} selected`}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Production</p>
                <p className="mt-2 text-sm font-semibold text-white">{productionDetailLabel()}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {STEPS.map((label, index) => {
                const tone = toneClasses(stageTone(selectedProject, index));
                return (
                  <button
                    key={label}
                    className={`rounded-2xl border px-4 py-4 text-left transition ${tone}`}
                    type="button"
                    aria-current={selectedStage === index ? "step" : undefined}
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
                </div>
              ) : null}
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(storyStatus.tone)}`}>
                <p className="font-semibold text-white">{storyStatus.label}</p>
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
                    <span className="text-sm text-slate-400" />
                  )}
                </div>
              </div>

              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Slots</p>
                    <p className="mt-2 text-lg font-semibold text-white">
                      {characterSlotSummary
                        ? `${characterSlotSummary.used_slots} / ${characterSlotSummary.total_slots} used`
                        : "Loading..."}
                    </p>
                  </div>
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={handlePurchaseCharacterSlots}
                    disabled={busy === "purchase-character-slots" || !creditSummary}
                  >
                    {busy === "purchase-character-slots"
                      ? "Updating..."
                      : characterSlotSummary
                        ? `Buy +${characterSlotSummary.addon_pack_size} Slots`
                        : "Buy More Slots"}
                  </button>
                </div>
                {characterLibraryFull ? (
                  <p className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    The saved character gallery is full. Buy more slots before adding another manual, uploaded, or AI-generated character.
                  </p>
                ) : null}
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
                        disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
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
                        disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
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
                      disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
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
                        disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
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
                        disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
                      />
                    </label>
                  </div>
                  <label className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
                    <input
                      className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-950 text-aurora"
                      type="checkbox"
                      checked={lockCharacterIdentity}
                      onChange={(event) => setLockCharacterIdentity(event.target.checked)}
                      disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
                    />
                    <span className="text-sm font-semibold text-white">Lock identity</span>
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Upload Your Character
                    </span>
                    <p className="text-xs text-slate-500">
                      Drop in an image to turn it into a saved character profile.
                    </p>
                    <input
                      className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none file:mr-4 file:rounded-full file:border-0 file:bg-aurora/10 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-aurora"
                      type="file"
                      accept="image/*"
                      onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                      disabled={!stageUnlocked(selectedProject, 2) || characterLibraryFull}
                    />
                  </label>
                  <div className="flex flex-wrap gap-3">
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("manual")}
                      disabled={
                        !selectedProject ||
                        !stageUnlocked(selectedProject, 2) ||
                        characterLibraryFull ||
                        busy === "character-manual"
                      }
                    >
                      {busy === "character-manual" ? "Creating..." : "Add Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("generate")}
                      disabled={
                        !selectedProject ||
                        !stageUnlocked(selectedProject, 2) ||
                        characterLibraryFull ||
                        busy === "character-generate"
                      }
                    >
                      {busy === "character-generate" ? "Generating..." : "Generate Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => handleCreateCharacter("upload")}
                      disabled={
                        !selectedProject ||
                        !stageUnlocked(selectedProject, 2) ||
                        characterLibraryFull ||
                        busy === "character-upload"
                      }
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
              {selectedProject?.workflow_state === "production_failed" || productionStatus?.queue_status === "failed" ? (
                <p className="mt-2 text-xs uppercase tracking-[0.28em] text-red-300">
                  Production failed
                </p>
              ) : null}
              {selectedProject &&
              stageUnlocked(selectedProject, 3) &&
              !["production_queued", "production_running", "video_completed", "production_failed"].includes(selectedProject.workflow_state) ? (
                <p className="mt-2 text-xs uppercase tracking-[0.28em] text-emerald-300">
                  Production ready
                </p>
              ) : null}
              <div className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${stepBannerClasses(productionStepStatus.tone)}`}>
                <p className="font-semibold text-white">{productionStepStatus.label}</p>
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
              {selectedProject?.workflow_state === "production_failed" || productionStatus?.queue_status === "failed" ? (
                <p className="mt-4 text-sm font-semibold text-red-100">
                  Production failed
                </p>
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
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Summary</p>
              {selectedProject ? (
                <>
                  <h3 className="mt-3 text-lg font-semibold text-white">
                    {selectedProject.title}
                  </h3>
                  <div className="mt-5 space-y-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Step</span>
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
                  <button
                    className="mt-5 rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                    type="button"
                    onClick={() => scrollToCreateStep(selectedStage)}
                  >
                Jump
                  </button>
                </>
              ) : (
                <div className="mt-3 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-4">
                  <p className="text-sm text-slate-300">No project selected.</p>
                </div>
              )}
            </div>
          </aside>
        </div>
      </section>
    );
  }

  function renderAutoCreate() {
    const customCharacterMode = autoCreateCustomCharacters.some((character) =>
      [character.name, character.role_type, character.description].some((value) => value.trim().length > 0)
    );
    const autoCreateProgressLabel =
      busy === "auto-create"
        ? "Creating..."
        : status === VIDEO_READY_MESSAGE || selectedProject?.workflow_state === "video_completed"
          ? VIDEO_READY_MESSAGE
          : "Waiting for process";
    return (
      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <h2 className="mt-2 text-2xl font-semibold text-white">Auto-Create</h2>
          <form id="auto-create-form" className="mt-[3px] space-y-[3px]" onSubmit={handleAutoCreate}>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-[3px]">
              <label htmlFor="auto-create-title" className="space-y-[3px]">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Video Title
                </span>
              </label>
              <div className="flex justify-end gap-[3px]">
                <div
                  className={`rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.26em] ${
                    busy === "auto-create"
                      ? "border-amber-400/35 bg-amber-400/10 text-amber-100"
                      : status === VIDEO_READY_MESSAGE || selectedProject?.workflow_state === "video_completed"
                        ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-100"
                        : "border-slate-700 bg-slate-900/70 text-slate-300"
                  }`}
                  aria-live="polite"
                >
                  {autoCreateProgressLabel}
                </div>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="submit"
                  disabled={busy === "auto-create"}
                >
                  {busy === "auto-create" ? "Creating..." : "Start"}
                </button>
              </div>
            </div>
            <input
              id="auto-create-title"
              className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
              placeholder="Enter the title"
              value={autoCreateTitle}
              onChange={(event) => setAutoCreateTitle(event.target.value)}
              required
            />
            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                Short Description
              </span>
              <textarea
                className="min-h-[92px] w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                placeholder="Optional short story description"
                value={autoCreateShortDescription}
                onChange={(event) => setAutoCreateShortDescription(event.target.value)}
              />
            </label>
            <label className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Genre
                </span>
                {isAutoCreateGenreFactual ? (
                  <span className="mt-2 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-amber-200">
                    Factual
                  </span>
                ) : null}
              </div>
              <div className="relative">
                <select
                  className={`w-full rounded-2xl border px-4 py-3 text-sm text-white outline-none ${
                    isAutoCreateGenreFactual
                      ? "border-amber-400/40 bg-amber-400/10"
                      : "border-slate-700 bg-slate-900/70"
                  } ${autoCreateGenre === "Wildlife/Animals" ? "pr-14" : ""}`}
                  value={autoCreateGenre}
                  onChange={(event) => handleAutoCreateGenreChange(event.target.value)}
                >
                  {AUTO_CREATE_GENRES.map((genre) => (
                    <option
                      key={genre.value}
                      value={genre.value}
                    >
                      {genre.label}
                    </option>
                  ))}
                </select>
                {autoCreateGenre === "Wildlife/Animals" ? (
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-white/90"
                  >
                    <WildlifeGenreMark />
                  </span>
                ) : null}
              </div>
              {isAutoCreateGenreFactual ? (
                <p className="text-[11px] leading-5 text-amber-200/75">
                  {isAutoCreateRealEvents
                    ? "Real Events uses factual research and narration-only production."
                    : "True Story uses factual research mode."}
                </p>
              ) : null}
            </label>
            <div className="rounded-3xl border border-slate-800 bg-slate-900/45 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Custom Cast
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    {isAutoCreateRealEvents
                      ? "Narration-only mode. Real Events does not use character generation."
                      : "Optional. Add up to 10 characters. Custom cast disables AI character generation."}
                  </p>
                </div>
                <button
                  className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  onClick={handleAddAutoCreateCharacterRow}
                  disabled={
                    isAutoCreateRealEvents ||
                    autoCreateCustomCharacters.length >= AUTO_CREATE_MAX_CUSTOM_CHARACTERS
                  }
                >
                  Add Character
                </button>
              </div>
              <div className="mt-4 space-y-4">
                {isAutoCreateRealEvents ? (
                  <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/80">
                    Character generation is disabled for Real Events.
                  </p>
                ) : customCharacterMode ? (
                  <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/80">
                    AI character generation is off for this run.
                  </p>
                ) : null}
                {autoCreateCustomCharacters.map((character, index) => (
                  <div key={character.id} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Character {index + 1}
                      </p>
                      <button
                        className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300"
                        type="button"
                        onClick={() => handleRemoveAutoCreateCharacterRow(character.id)}
                      >
                        Remove
                      </button>
                    </div>
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                          Character Name
                        </span>
                        <input
                          className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                          placeholder="Character name"
                          value={character.name}
                          onChange={(event) => handleUpdateAutoCreateCharacterRow(character.id, "name", event.target.value)}
                        />
                      </label>
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                          Role Type
                        </span>
                        <select
                          className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                          value={character.role_type}
                          onChange={(event) => handleUpdateAutoCreateCharacterRow(character.id, "role_type", event.target.value)}
                        >
                          <option value="main">Main</option>
                          <option value="supporting">Supporting</option>
                          <option value="extra">Extra</option>
                          <option value="npc">NPC</option>
                        </select>
                      </label>
                    </div>
                    <label className="mt-4 block space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Description
                      </span>
                      <textarea
                        className="min-h-[88px] w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                        placeholder="Optional character detail"
                        value={character.description}
                        onChange={(event) => handleUpdateAutoCreateCharacterRow(character.id, "description", event.target.value)}
                      />
                    </label>
                  </div>
                ))}
                {autoCreateCustomCharacters.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    Leave this empty to let Auto-Create generate the cast for you.
                  </div>
                ) : null}
              </div>
            </div>
            <div className="rounded-3xl border border-slate-800 bg-slate-900/45 p-4">
              <button
                className="flex w-full items-start justify-between gap-4 text-left"
                type="button"
                onClick={() => setAutoCreateCharacterPanelOpen((value) => !value)}
                aria-expanded={autoCreateCharacterPanelOpen}
              >
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Character Builder
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    Add, generate, or upload characters from Auto-Create and save them to the library.
                  </p>
                </div>
                <span className="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                  {autoCreateCharacterPanelOpen ? "Collapse" : "Expand"}
                </span>
              </button>
              {autoCreateCharacterPanelOpen ? (
                <div className="mt-4 space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Character Name</span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        placeholder="My Main Character"
                        value={libraryCharacterName}
                        onChange={(event) => setLibraryCharacterName(event.target.value)}
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Role</span>
                      <select
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        value={libraryCharacterRole}
                        onChange={(event) => setLibraryCharacterRole(event.target.value)}
                      >
                        <option value="main">Main</option>
                        <option value="supporting">Supporting</option>
                        <option value="extra">Extra</option>
                        <option value="npc">NPC</option>
                      </select>
                    </label>
                    <label className="space-y-2 sm:col-span-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Description</span>
                      <textarea
                        className="min-h-[100px] w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        placeholder="A short description of the character"
                        value={libraryCharacterDescription}
                        onChange={(event) => setLibraryCharacterDescription(event.target.value)}
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Traits</span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        placeholder="brave, witty, curious"
                        value={libraryCharacterTraits}
                        onChange={(event) => setLibraryCharacterTraits(event.target.value)}
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Voice Profile</span>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none"
                        value={libraryCharacterVoice}
                        onChange={(event) => setLibraryCharacterVoice(event.target.value)}
                      />
                    </label>
                    <label className="space-y-2 sm:col-span-2">
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        Upload Your Character
                      </span>
                      <p className="text-xs text-slate-500">
                        Optional. Upload an image or skip it for a text-only character.
                      </p>
                      <input
                        className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none file:mr-4 file:rounded-full file:border-0 file:bg-aurora/10 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-aurora"
                        type="file"
                        accept="image/*"
                        onChange={(event) => setLibraryUploadFile(event.target.files?.[0] ?? null)}
                      />
                    </label>
                    <label className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 sm:col-span-2">
                      <input
                        className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-950 text-aurora"
                        type="checkbox"
                        checked={libraryLockCharacterIdentity}
                        onChange={(event) => setLibraryLockCharacterIdentity(event.target.checked)}
                      />
                      <span className="text-sm font-semibold text-white">Lock identity</span>
                    </label>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => void handleLibraryCharacterAction("manual")}
                      disabled={busy === "library-character-manual"}
                    >
                      {busy === "library-character-manual" ? "Saving..." : "Add Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => void handleLibraryCharacterAction("generate")}
                      disabled={busy === "library-character-generate"}
                    >
                      {busy === "library-character-generate" ? "Generating..." : "Generate Character"}
                    </button>
                    <button
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      onClick={() => void handleLibraryCharacterAction("upload")}
                      disabled={busy === "library-character-upload"}
                    >
                      {busy === "library-character-upload" ? "Uploading..." : "Upload Character"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            <label className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Duration
                </span>
                <span className="rounded-full border border-slate-800 bg-slate-900/80 px-3 py-1 text-xs font-semibold text-white">
                  {autoCreateDuration} min
                </span>
              </div>
              <input
                className="w-full accent-aurora"
                type="range"
                min={1}
                max={autoCreateAvailableDuration}
                step={1}
                value={autoCreateDuration}
                onChange={(event) => {
                  const next = Number(event.target.value) || 1;
                  setAutoCreateDuration(Math.max(1, Math.min(autoCreateAvailableDuration, next)));
                }}
              />
              <p className="text-xs text-slate-500">
                Max {autoCreateAvailableDuration} minutes. The final duration is auto-capped to your available credits before production starts.
              </p>
            </label>
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      Start Credits
                    </span>
                    <span className="rounded-full border border-slate-800 bg-slate-900/70 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                      Optional
                    </span>
                  </div>
                  <textarea
                    className="min-h-[112px] w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                    placeholder="Opening title, cast, crew, studio name..."
                    value={autoCreateStartCredits}
                    onChange={(event) => setAutoCreateStartCredits(event.target.value)}
                  />
                </label>
                <label className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      End Credits
                    </span>
                    <span className="rounded-full border border-slate-800 bg-slate-900/70 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                      Optional
                    </span>
                  </div>
                  <textarea
                    className="min-h-[112px] w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                    placeholder="Rolling cast, production crew, thanks..."
                    value={autoCreateEndCredits}
                    onChange={(event) => setAutoCreateEndCredits(event.target.value)}
                  />
                </label>
              </div>
            </form>
          </div>
      </section>
    );
  }

  function renderLibrary() {
    const scriptsTab = approvedScripts;
    const videosTab = completedVideos;
    return (
      <section className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="mt-2 text-2xl font-semibold text-white">Library</h2>
          </div>
          <button
            className="rounded-full border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            disabled={busy === "delete-projects" || projects.length === 0}
            onClick={() => void handleDeleteAllProjects("library")}
          >
            {busy === "delete-projects" ? "Deleting..." : "Delete all projects"}
          </button>
        </div>
        <div className="flex flex-wrap gap-3">
          {(["characters", "scripts", "videos"] as LibraryTab[]).map((tab) => (
            <button
              key={tab}
              data-active-glow={libraryTab === tab ? "true" : undefined}
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
              </article>
            ))}
            {visibleCharacterLibrary.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
                No saved characters yet. Add one above or upload your own preferred character.
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
                      <button
                        className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200"
                        type="button"
                        onClick={() => {
                          setPublishProjectId(project.project_id);
                          setActiveNav("downloads");
                        }}
                      >
                        Open
                      </button>
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
              <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400" />
            ) : null}
          </div>
        ) : null}
      </section>
    );
  }

  function renderPublish() {
    const targetProject = publishProject;
    const selectedConnection =
      socialConnections.find((connection) => connection.connection_id === socialConnectionId) ??
      socialConnections[0] ??
      null;
    const selectedConnectionId = selectedConnection?.connection_id ?? null;
    const selectedPublishBusy = selectedConnectionId ? busy === `social-publish-${selectedConnectionId}` : false;
    const canSingleSend = Boolean(targetProject && selectedConnectionId);
    const canBulkSend = Boolean(targetProject && socialConnections.length > 0);
    const publishActionBusy = publishSendMode === "single" ? selectedPublishBusy : busy === "social-publish-all";
    const publishActionLabel = "Send now";
    return (
      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-2xl font-semibold text-white">Publish</h2>
            <select
              className="rounded-full border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-200"
              value={targetProject?.project_id ?? ""}
              onChange={(event) => setPublishProjectId(event.target.value || null)}
            >
              <option value="">Select finished video</option>
              {completedVideos.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.title}
                </option>
              ))}
            </select>
          </div>

          {targetProject ? (
            <>
              <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <h3 className="text-xl font-semibold text-white">{targetProject.title}</h3>
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={() =>
                      publishSendMode === "single"
                        ? void handlePublishConnection(selectedConnectionId ?? "")
                        : void handlePublishAllConnected()
                    }
                    disabled={
                      publishActionBusy ||
                      socialLoading ||
                      (publishSendMode === "single" ? !canSingleSend || !selectedConnectionId : !canBulkSend)
                    }
                  >
                    {publishActionBusy ? "Sending..." : publishActionLabel}
                  </button>
                </div>
                <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Caption</p>
                  <textarea
                    className="mt-3 min-h-28 w-full rounded-2xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500"
                    value={publishCaption}
                    onChange={(event) => setPublishCaption(event.target.value)}
                    placeholder="Write the caption that should accompany the publish."
                  />
                </div>
              </div>

              {socialError ? (
                <p className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                  {socialError}
                </p>
              ) : null}
              {socialStatus ? (
                <p className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                  {socialStatus}
                </p>
              ) : null}
              {publishStatus ? (
                <p className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                  {publishStatus}
                </p>
              ) : null}

              <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
                <div className="flex items-center justify-between gap-4">
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Connected accounts</p>
                  <div className="text-right text-xs text-slate-500">
                    {socialLoading ? "Refreshing..." : `${socialConnections.length} connected`}
                  </div>
                </div>
                <div className="mt-5 grid gap-3">
                  {socialConnections.length > 0 ? (
                    socialConnections.map((connection) => {
                      const selected = selectedConnection?.connection_id === connection.connection_id;
                      return (
                        <div
                          key={connection.connection_id}
                          data-active-glow={selected ? "true" : undefined}
                          className={`rounded-2xl border p-4 transition ${
                            selected
                              ? "border-white/95 bg-white/5"
                              : "border-slate-800 bg-slate-900/55"
                          }`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300">
                                <span className="inline-flex h-4 w-4 items-center justify-center text-white">
                                  <SocialPlatformMark platform={connection.platform} />
                                </span>
                                {socialPlatformLabel(connection.platform)}
                              </div>
                              <p className="text-sm font-semibold text-white">{connection.account_label}</p>
                              <p className="mt-2 text-sm text-slate-400">
                                {connection.account_identifier || "No public identifier saved"}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                type="button"
                                onClick={() => setSocialConnectionId(connection.connection_id)}
                              >
                                {selected ? "Selected" : "Select"}
                              </button>
                              <button
                                className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                type="button"
                                disabled={busy === `social-delete-${connection.connection_id}`}
                                onClick={() => void handleDeleteSocialAccount(connection.connection_id)}
                              >
                                Remove
                              </button>
                            </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                          <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                            {connection.enabled ? "Ready" : "Disabled"}
                          </span>
                          {selected ? (
                            <span className="rounded-full border border-white/90 bg-white/5 px-2 py-1 text-white">
                              Active
                            </span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })
                ) : (
                    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                      No connected accounts yet.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
                <div className="flex items-center justify-between gap-4">
                  <h3 className="text-xl font-semibold text-white">Recent jobs</h3>
                </div>
                <div className="mt-5 grid gap-3">
                  {publishQueue.length > 0 ? (
                    publishQueue.map((entry) => (
                      <div
                        key={entry.job_id}
                        className="rounded-2xl border border-slate-800 bg-slate-900/55 p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">{socialPlatformLabel(entry.platform)}</p>
                            <p className="mt-1 text-xs text-slate-500">{entry.connection_id}</p>
                          </div>
                          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{entry.status}</p>
                        </div>
                        {entry.published_url ? (
                          <a
                            className="mt-3 inline-flex text-sm text-aurora hover:text-cyan-200"
                            href={entry.published_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open published post
                          </a>
                        ) : null}
                        {entry.error_message ? (
                          <p className="mt-3 text-sm text-red-200">{entry.error_message}</p>
                        ) : null}
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                      No publish jobs yet.
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-sm text-slate-400">
              Select a finished video to publish.
            </div>
          )}
        </div>

        <aside className="space-y-6">
          <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {SOCIAL_PLATFORM_OPTIONS.map((option) => {
                const selected = socialPlatform === option.key;
                return (
                  <button
                    key={option.key}
                    data-active-glow={selected ? "true" : undefined}
                    className={`flex flex-col items-center gap-2 rounded-3xl border px-2 py-3 text-[11px] uppercase tracking-[0.15em] transition ${
                      selected
                        ? "border-white/95 bg-white/5 text-white"
                        : "border-slate-800 bg-slate-950 text-slate-300"
                    }`}
                    type="button"
                    onClick={() => {
                      setSocialPlatform(option.key);
                      setSocialSettingsOpenPlatform((current) => (current === option.key ? null : option.key));
                    }}
                    aria-pressed={selected}
                    aria-label={option.label}
                  >
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-700 bg-slate-900/80 text-white">
                      <SocialPlatformMark platform={option.key} />
                    </span>
                    <span>{option.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="mt-[3px] flex items-center justify-between gap-3 pr-[3px]">
              <div className="flex-1 min-w-0 max-w-[180px]">
                <button
                  role="tab"
                  aria-selected={publishSendMode === "single"}
                  data-active-glow={publishSendMode === "single" ? "true" : undefined}
                  className={`w-full whitespace-nowrap rounded-xl border px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] transition ${
                    publishSendMode === "single"
                      ? "border-white/95 bg-white/5 text-white"
                      : "border-slate-800 bg-slate-950/70 text-slate-400 hover:text-slate-200"
                  }`}
                  type="button"
                  onClick={() => setPublishSendMode("single")}
                >
                  Single send
                </button>
              </div>
              <div className="flex-1 min-w-0 max-w-[180px]">
                <button
                  role="tab"
                  aria-selected={publishSendMode === "bulk"}
                  data-active-glow={publishSendMode === "bulk" ? "true" : undefined}
                  className={`w-full whitespace-nowrap rounded-xl border px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] transition ${
                    publishSendMode === "bulk"
                      ? "border-white/95 bg-white/5 text-white"
                      : "border-slate-800 bg-slate-950/70 text-slate-400 hover:text-slate-200"
                  }`}
                  type="button"
                  onClick={() => setPublishSendMode("bulk")}
                >
                  Bulk send
                </button>
              </div>
            </div>

            <div
              className={`overflow-hidden rounded-3xl border transition-all duration-200 ${
                socialSettingsOpenPlatform
                  ? "max-h-[28rem] border-slate-800 bg-slate-950/70 opacity-100"
                  : "max-h-0 border-transparent bg-transparent opacity-0 pointer-events-none"
              }`}
            >
              <form className="space-y-4 p-6 pt-5" onSubmit={(event) => void handleSaveSocialConnection(event)}>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    {socialPlatformLabel(socialPlatform)}
                  </p>
                  <div className="mt-[3px] grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-2 text-sm text-slate-200">
                      <span
                        className="flex min-h-[2.75rem] items-start text-xs uppercase leading-tight tracking-[0.2em] text-slate-500"
                        style={{ transform: "translateY(-3px)" }}
                      >
                        Account label
                      </span>
                      <input
                        className="h-14 rounded-2xl border border-slate-800 bg-slate-950 px-3 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500"
                        value={socialAccountLabel}
                        onChange={(event) => setSocialAccountLabel(event.target.value)}
                        placeholder="My Main Channel"
                      />
                    </label>
                    <label className="grid gap-2 text-sm text-slate-200">
                      <span
                        className="flex min-h-[2.75rem] flex-col items-start justify-start leading-tight text-slate-500"
                        style={{ transform: "translateY(-19px)" }}
                      >
                        <span className="text-xs uppercase tracking-[0.2em]">{socialPlatformLabel(socialPlatform)}</span>
                        <span className="text-xs uppercase tracking-[0.2em]">Account ID</span>
                      </span>
                      <input
                        className="h-14 rounded-2xl border border-slate-800 bg-slate-950 px-3 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500"
                        value={socialAccountIdentifier}
                        onChange={(event) => setSocialAccountIdentifier(event.target.value)}
                        placeholder="Account identifier"
                      />
                    </label>
                  </div>
                </div>
                <button
                  className="w-full rounded-2xl border border-aurora/40 bg-aurora/10 px-4 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                  type="submit"
                  disabled={socialSaving}
                >
                  {socialSaving ? "Saving..." : "Save account"}
                </button>
              </form>
            </div>
          </div>

          {selectedConnection ? (
            <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
                <div className="flex items-start gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-700 bg-slate-900/80 text-white">
                    <SocialPlatformMark platform={selectedConnection.platform} />
                  </span>
                  <div>
                    <p className="font-semibold text-white">{socialPlatformLabel(selectedConnection.platform)}</p>
                    <p className="mt-1 text-slate-400">{selectedConnection.account_identifier || "No identifier"}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </aside>
      </section>
    );
  }

  function renderCommunity() {
    const pinnedTopics = [
      {
        subject: "Feature ideas",
        message: "Share one feature that would make X'treamers better for your workflow.",
      },
      {
        subject: "Production tips",
        message: "Post a short tip for scripting, pacing, or finishing videos faster.",
      },
      {
        subject: "Showcase wins",
        message: "Show a finished project, a lesson learned, or a result you’re proud of.",
      },
    ];

    return (
      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Community</p>
              <h2 className="mt-2 text-2xl font-semibold text-white">X&apos;treamers</h2>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                A place for X&apos;treamers users to join the discussion, share feature ideas, and swap production notes.
              </p>
            </div>
            <div className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs uppercase tracking-[0.2em] text-slate-400">
              {communityPosts.length} posts
            </div>
          </div>

          {communityError ? (
            <p className="mt-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              {communityError}
            </p>
          ) : null}
          {communityStatus ? (
            <p className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              {communityStatus}
            </p>
          ) : null}

          <div className="mt-6">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Pinned topics</p>
              <span className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1 text-[10px] uppercase tracking-[0.24em] text-slate-500">
                Start here
              </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {pinnedTopics.map((topic) => (
                <button
                  key={topic.subject}
                  className="rounded-2xl border border-slate-800 bg-slate-900/55 p-4 text-left transition hover:border-aurora/30 hover:bg-slate-900/75"
                  type="button"
                  onClick={() => setCommunitySubject(topic.subject)}
                >
                  <p className="text-sm font-semibold text-white">{topic.subject}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{topic.message}</p>
                  <p className="mt-4 text-[10px] uppercase tracking-[0.2em] text-slate-500">Use topic</p>
                </button>
              ))}
            </div>
          </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <form className="space-y-4" onSubmit={handleSubmitCommunityPost}>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Topic</span>
                <input
                  className="w-full rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                  value={communitySubject}
                  onChange={(event) => setCommunitySubject(event.target.value)}
                  placeholder="Feature idea"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Message</span>
                <textarea
                  className="min-h-[160px] w-full rounded-3xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
                  value={communityMessage}
                  onChange={(event) => setCommunityMessage(event.target.value)}
                  placeholder="Share an idea, ask a question, or start a discussion."
                />
              </label>
              <button
                className="rounded-full border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:opacity-50"
                type="submit"
                disabled={communitySending}
              >
                {communitySending ? "Posting..." : "Post"}
              </button>
            </form>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Recent discussions</p>
                <button
                  className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-200"
                  type="button"
                  onClick={() => void refreshCommunityPosts()}
                  disabled={communityLoading}
                >
                  {communityLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>
              <div className="grid gap-3">
                {communityLoading ? (
                  <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                    Loading community posts...
                  </div>
                ) : communityPosts.length > 0 ? (
                  communityPosts.map((post) => (
                    <article key={post.post_id} className="rounded-2xl border border-slate-800 bg-slate-900/55 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-white">{post.subject}</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                            {post.author_label}
                          </p>
                        </div>
                        <p className="text-xs text-slate-500">{new Date(post.created_at).toLocaleString()}</p>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-300">{post.message}</p>
                      <div className="mt-4 flex items-center justify-between gap-3">
                        <button
                          className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-200 transition hover:border-aurora/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                          type="button"
                          disabled={communityReactingPostId === post.post_id}
                          onClick={() => void handleApplaudCommunityPost(post.post_id)}
                        >
                          {communityReactingPostId === post.post_id ? "Applauding..." : "Applaud"}
                        </button>
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                          {post.applause_count} applause
                        </p>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
                    Be the first to start a discussion in X&apos;treamer.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }

  function renderDownloads() {
    const targetProject = downloadProject;
    const finalVideoUrl = targetProject?.final_video_url || "";
    return (
      <section className="grid min-h-0 gap-6 xl:grid-cols-[0.68fr_1.32fr]">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Download</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Completed video</h2>
          <div className="mt-5">
            <select
              className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-200"
              value={targetProject?.project_id ?? ""}
              onChange={(event) => setPublishProjectId(event.target.value || null)}
            >
              <option value="">Select completed project</option>
              {completedVideos.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.title}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-5">
            {finalVideoUrl ? (
              <a
                className="inline-flex rounded-2xl border border-aurora/40 bg-aurora/10 px-4 py-3 text-sm font-semibold text-aurora"
                href={finalVideoUrl}
                download
              >
                Download
              </a>
            ) : (
              <p className="text-sm text-slate-400">No completed video is available yet.</p>
            )}
          </div>
        </div>
      </section>
    );
  }

  function renderFactoryMode() {
    return (
      <section className="space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Autonomous production</p>
              <h2 className="mt-2 text-2xl font-semibold text-white">Factory Mode</h2>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Continuous video production and distribution to connected social platforms stays locked until
                deployment explicitly enables it.
              </p>
            </div>
            <div className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs uppercase tracking-[0.2em] text-slate-400">
              {factoryModeDeploymentEnabled ? (factoryModeActivated ? "Unlocked" : "Locked") : "Locked"}
            </div>
          </div>

          {factoryModeDeploymentEnabled ? (
            factoryModeActivated ? (
              <div className="mt-6 grid max-h-[calc(100vh-14rem)] gap-6 overflow-y-auto pr-1 lg:grid-cols-[1fr_auto]">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Factory queue</p>
                    <span
                      className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${
                        factoryModeRunnerStatus?.enabled === false
                          ? "border-slate-700 bg-slate-900/70 text-slate-500"
                          : factoryModeRunnerStatus?.running
                            ? "border-aurora/40 bg-aurora/10 text-aurora"
                            : "border-slate-700 bg-slate-900/70 text-slate-400"
                      }`}
                    >
                      {factoryModeRunnerStatus?.enabled === false
                        ? "Worker managed"
                        : factoryModeRunnerStatus?.running
                          ? "Runner live"
                          : "Ready"}
                    </span>
                  </div>
                  <p className="mt-3 leading-6 text-slate-300">
                    Add one title per line. Factory Mode will generate each project in order, then publish each finished
                    video to every connected platform until titles or credits run out.
                  </p>
                  <textarea
                    className="mt-4 min-h-[9rem] w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-200 outline-none transition placeholder:text-slate-500 focus:border-aurora/50"
                    placeholder="Launch title one&#10;Launch title two&#10;Launch title three"
                    value={factoryModeTitleQueue}
                    onChange={(event) => setFactoryModeTitleQueue(event.target.value)}
                  />
                  <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                    The queue is processed in order and published to every connected platform.
                  </p>
                  {factoryModeMessage ? <p className="mt-3 text-sm text-aurora">{factoryModeMessage}</p> : null}
                  {factoryModeError ? <p className="mt-3 text-sm text-rose-300">{factoryModeError}</p> : null}
                </div>
                <div className="space-y-[3px]">
                  <button
                    className="w-full rounded-2xl border border-aurora/40 bg-aurora/10 px-5 py-3 text-sm font-semibold text-aurora disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-900/55 disabled:text-slate-500"
                    type="button"
                    disabled={busy === "factory-mode-start" || factoryModeQueueTitles.length === 0}
                    onClick={handleStartFactoryMode}
                  >
                    Start factory run
                  </button>
                  <button
                    className="w-full rounded-2xl border border-slate-800 bg-slate-900/55 px-5 py-3 text-sm font-semibold text-slate-300 disabled:cursor-not-allowed disabled:text-slate-500"
                    type="button"
                    disabled={busy === "factory-mode-stop"}
                    onClick={handleStopFactoryMode}
                  >
                    Stop run
                  </button>
                </div>
              </div>
            ) : (
            <div className="mt-6 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-6">
              <p className="text-xs uppercase tracking-[0.25em] text-amber-100/80">Access required</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Unlock Factory Mode</h3>
              <p className="mt-2 max-w-2xl text-sm text-amber-50/80">
                Factory Mode is deployed but locked until you purchase one-time access or a subscription in Credits & Plans.
              </p>
              <button
                className="mt-4 rounded-full border border-amber-300/40 bg-amber-300/10 px-4 py-2 text-sm font-semibold text-amber-50"
                type="button"
                onClick={handleOpenCreditPanel}
              >
                Open Credits & Plans
              </button>
            </div>
            )
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-sm text-slate-400">
              Factory Mode is locked until this deployment sets{" "}
              <span className="font-semibold text-slate-200">NEXT_PUBLIC_FACTORY_MODE_ENABLED=true</span>.
            </div>
          )}
        </div>
      </section>
    );
  }

  function renderPlayVideo() {
    const targetProject = publishProject;
    const showPlayControls = playVideoControlsVisible || !targetProject?.final_video_url;
    return (
      <section
        className={`relative flex flex-1 min-h-0 overflow-hidden ${
          playbackMode ? "bg-black" : "rounded-[2px] border border-slate-900 bg-black/95 shadow-2xl shadow-black/50"
        }`}
      >
        <div className="absolute inset-0">
          {targetProject?.final_video_url ? (
            <video
              className="h-full w-full object-contain bg-black"
              controls
              controlsList="nodownload noplaybackrate noremoteplayback"
              disablePictureInPicture
              playsInline
              autoPlay
              src={targetProject.final_video_url}
            />
          ) : (
            <div className="flex h-full items-center justify-center bg-black px-8 text-sm text-slate-400">
              Select a completed video to start playback.
            </div>
          )}
        </div>

        <div
          className={`absolute left-4 top-4 z-10 w-[min(28rem,calc(100%-2rem))] transition duration-200 ${
            showPlayControls ? "translate-y-0 opacity-100" : "-translate-y-2 opacity-0 pointer-events-none"
          }`}
        >
          <div className="rounded-3xl border border-slate-800 bg-slate-950/85 p-5 backdrop-blur-xl">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Playback</p>
                <h2 className="mt-2 text-lg font-semibold text-white">Final video validation</h2>
              </div>
              <button
                className="rounded-full border border-slate-800 bg-slate-900/80 px-3 py-1 text-xs text-slate-300"
                type="button"
                onClick={() => setActiveNav("create")}
              >
                Exit theater
              </button>
            </div>
            <div className="mt-4">
              <select
                className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-200"
                value={targetProject?.project_id ?? ""}
                onChange={(event) => setPublishProjectId(event.target.value || null)}
              >
                <option value="">Select finished video</option>
                {completedVideos.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Status</p>
              <p className="mt-2 text-sm text-white">
                {targetProject?.workflow_state === "video_completed" ? "Ready for playback" : "Select a completed project"}
              </p>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <button
                className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-300"
                type="button"
                onClick={() => setPlayVideoControlsVisible((value) => !value)}
              >
                {showPlayControls ? "Hide controls" : "Show controls"}
              </button>
              <button
                className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-300"
                type="button"
                onClick={() => {
                  if (isPlayFullscreen) {
                    void exitPlayFullscreen();
                  } else {
                    void enterPlayFullscreen();
                  }
                }}
              >
                {isPlayFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              </button>
              <p className="text-[11px] uppercase tracking-[0.25em] text-slate-500">
                Move the mouse to reveal the dock
              </p>
            </div>
          </div>
        </div>
        {targetProject?.final_video_url ? (
          <button
            className={`absolute bottom-4 right-4 z-10 rounded-full border border-slate-700 bg-slate-950/80 px-4 py-2 text-xs font-semibold text-slate-200 backdrop-blur-xl transition ${
              showPlayControls ? "opacity-0 pointer-events-none" : "opacity-100"
            }`}
            type="button"
            onClick={() => setPlayVideoControlsVisible(true)}
          >
            Show controls
          </button>
        ) : null}
      </section>
    );
  }

  const workflowProgressPanel = null;

  return (
    <div ref={appShellRef} className="relative h-screen overflow-hidden bg-midnight text-slate-100">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(244,114,182,0.12),transparent_30%)]" />

      {mobileDrawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            aria-label="Close navigation drawer"
            className="absolute inset-0 bg-slate-950/70"
            type="button"
            onClick={() => setMobileDrawerOpen(false)}
          />
          <aside className="absolute right-0 top-0 flex h-full w-[min(88vw,17rem)] flex-col overflow-y-auto border-l border-slate-800 bg-slate-950/95 p-5 shadow-2xl shadow-black/40">
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col">
                <img className="h-[183px] w-auto -translate-y-[47px] object-contain" src={XTREAM_LOGO_SRC} alt="X'tream" />
                <p className="relative -top-[110px] mt-[3px] text-[11px] font-bold uppercase tracking-[0.35em] text-white">
                  Production Dashboard
                </p>
              </div>
              <button
                className="rounded-full border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200"
                type="button"
                onClick={() => setMobileDrawerOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="-translate-y-[50px]">
              <nav className="mt-[-55px] space-y-3" aria-label="Primary mobile drawer">
                {NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    data-active-glow={activeNav === item.id ? "true" : undefined}
                    className={`w-full rounded-3xl border p-4 text-left transition ${
                      activeNav === item.id
                        ? "border-aurora/40 bg-aurora/10 text-white"
                        : "border-slate-800 bg-slate-900/55 text-slate-300"
                    }`}
                    type="button"
                    onClick={() => handleNavSelect(item.id)}
                  >
                    <p className="text-sm font-semibold">{item.label}</p>
                    </button>
                ))}
              </nav>
              <div className="mt-auto space-y-[3px] pt-6">
                {FOOTER_NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    data-active-glow={activeNav === item.id ? "true" : undefined}
                    className={`w-full rounded-3xl border p-4 text-left transition ${
                      activeNav === item.id
                        ? "border-white/95 bg-white/5 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_0_14px_rgba(255,255,255,0.12),0_0_18px_rgba(125,211,252,0.48),0_0_34px_rgba(59,130,246,0.40),0_0_52px_rgba(37,99,235,0.24)]"
                        : "border-slate-800 bg-slate-900/55 text-slate-300"
                    }`}
                    type="button"
                    onClick={() => handleNavSelect(item.id)}
                  >
                    <p className="text-sm font-semibold">{item.label}</p>
                  </button>
                ))}
              </div>
            </div>
          </aside>
        </div>
      ) : null}

      <div className="flex h-full min-h-0">
        <aside
          className={playbackMode ? "hidden" : "hidden h-full w-[15rem] shrink-0 flex-col border-r border-slate-900/80 bg-slate-950/85 p-4 lg:flex"}
        >
          <div>
            <img className="h-[187px] w-auto -translate-y-[47px] object-contain" src={XTREAM_LOGO_SRC} alt="X'tream" />
            <p className="relative -top-[110px] mt-[3px] text-[11px] font-bold uppercase tracking-[0.35em] text-white">
              Production Dashboard
            </p>
            <div className="-translate-y-[50px]">
              <nav className="mt-[-55px] space-y-[3px]" aria-label="Primary">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  data-active-glow={activeNav === item.id ? "true" : undefined}
                  className={`w-full rounded-2xl border px-3 py-2.5 text-left transition ${
                    activeNav === item.id
                      ? "border-white/95 bg-white/5 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_0_14px_rgba(255,255,255,0.12),0_0_18px_rgba(125,211,252,0.48),0_0_34px_rgba(59,130,246,0.40),0_0_52px_rgba(37,99,235,0.24)]"
                      : "border-slate-800 bg-slate-900/45 text-slate-300 hover:border-slate-700 hover:bg-slate-900/60"
                  }`}
                  type="button"
                  onClick={() => handleNavSelect(item.id)}
                >
                  <p className="text-[12px] font-semibold">{item.label}</p>
                  </button>
              ))}
              </nav>
              <div className="mt-[3px] space-y-[3px]">
                {FOOTER_NAV_ITEMS.map((item) => (
                  <button
                    key={item.id}
                    data-active-glow={activeNav === item.id ? "true" : undefined}
                    className={`w-full rounded-2xl border px-3 py-2.5 text-left transition ${
                      activeNav === item.id
                        ? "border-white/95 bg-white/5 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_0_14px_rgba(255,255,255,0.12),0_0_18px_rgba(125,211,252,0.48),0_0_34px_rgba(59,130,246,0.40),0_0_52px_rgba(37,99,235,0.24)]"
                        : "border-slate-800 bg-slate-900/45 text-slate-300 hover:border-slate-700 hover:bg-slate-900/60"
                    }`}
                    type="button"
                    onClick={() => handleNavSelect(item.id)}
                  >
                    <p className="text-[12px] font-semibold">{item.label}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>

        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {!playbackMode ? (
            <header className="shrink-0 border-b border-slate-900/70 bg-slate-950/80 backdrop-blur">
            <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
              <div className="min-w-0">
                <h2 className="truncate text-[1.4rem] font-semibold text-white">
                  AI Assisted Video Production Tool
                </h2>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-3">
                <button
                  className="rounded-full border border-slate-800 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 lg:hidden"
                  type="button"
                  onClick={() => setMobileDrawerOpen(true)}
                >
                  Menu
                </button>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora transition hover:border-aurora/60 hover:bg-aurora/15 hover:text-white"
                    type="button"
                    onClick={handleOpenCreditPanel}
                    aria-haspopup="dialog"
                    aria-expanded={showCreditPanel}
                  >
                    SUBSCRIBE
                  </button>
                  <div
                    className="rounded-full border border-aurora/35 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora shadow-[inset_0_0_0_1px_rgba(34,211,238,0.10)]"
                    aria-label="Credit usage summary"
                    aria-live="polite"
                  >
                    {isAuthenticated ? (
                      <>
                        Credits: {creditBalance ?? "—"} left{creditTotal !== null ? ` • used ${creditUsedTotal ?? "—"} / ${creditTotal}` : ""}
                        {characterSlotSummary
                          ? ` • Characters ${characterSlotSummary.used_slots}/${characterSlotSummary.total_slots}`
                          : ""}
                      </>
                    ) : "Explore Mode"}
                  </div>
                </div>
              </div>
            </div>
              <div className="border-t border-slate-900/60 px-4 py-3 sm:px-6 lg:hidden">
              <nav className="grid grid-cols-2 gap-3" aria-label="Primary mobile">
                {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  className={`rounded-2xl border px-4 py-3 text-left transition ${mobileNavClasses(activeNav === item.id)}`}
                  type="button"
                  onClick={() => handleNavSelect(item.id)}
                >
                  <p className="text-sm font-semibold">{item.label}</p>
                </button>
              ))}
            </nav>
            <div className="mt-[3px] grid grid-cols-2 gap-3">
              {FOOTER_NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  data-active-glow={activeNav === item.id ? "true" : undefined}
                  className={`rounded-2xl border px-4 py-3 text-left transition ${mobileNavClasses(activeNav === item.id)}`}
                  type="button"
                  onClick={() => handleNavSelect(item.id)}
                >
                  <p className="text-sm font-semibold">{item.label}</p>
                </button>
              ))}
            </div>
            </div>
            </header>
          ) : null}

          <div className={playbackMode ? "min-h-0 flex-1 overflow-hidden" : "min-h-0 flex-1 overflow-y-auto"}>
            <div
              className={
                playbackMode
                  ? "flex h-full w-full min-h-0 flex-col gap-0 px-0 py-0"
                  : "mx-auto flex w-full max-w-[1600px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6"
              }
            >
              {workflowProgressPanel}
              {!playbackMode && error ? (
                <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                  {error}
                </div>
              ) : null}
              {!playbackMode && status ? (
                <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                  {status}
                </div>
              ) : null}
              {!playbackMode && loading ? (
                <div className="rounded-3xl border border-slate-800 bg-slate-950/70 p-10 text-sm text-slate-400">
                  Loading...
                </div>
              ) : null}
              {!loading && activeNav === "overview" ? renderOverview() : null}
              {!loading && activeNav === "projects" ? renderProjects() : null}
              {!loading && activeNav === "create" ? renderCreate() : null}
              {!loading && activeNav === "auto-create" ? renderAutoCreate() : null}
              {!loading && activeNav === "library" ? renderLibrary() : null}
              {!loading && activeNav === "publish" ? renderPublish() : null}
              {!loading && activeNav === "transaction-records" ? renderTransactionRecords() : null}
              {!loading && activeNav === "factory-mode" ? renderFactoryMode() : null}
              {!loading && activeNav === "community" ? renderCommunity() : null}
              {!loading && activeNav === "downloads" ? renderDownloads() : null}
              {!loading && activeNav === "play" ? renderPlayVideo() : null}
              {!loading && activeNav === "feedback" ? renderFeedback() : null}
            </div>
          </div>
        </main>
      </div>
      {showCreditPanel ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/70 px-4 py-6 backdrop-blur-sm"
          role="presentation"
          onClick={handleCloseCreditPanel}
        >
          <div
            className="flex w-full max-w-4xl max-h-[calc(100vh-3rem)] flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 p-5 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label="Credit purchase panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="shrink-0">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold text-white">Credits & Plans</h2>
                </div>
                <button
                  className="rounded-full border border-slate-800 px-3 py-1 text-xs text-slate-300"
                  type="button"
                  onClick={handleCloseCreditPanel}
                >
                  Close
                </button>
              </div>
              {isAuthenticated ? (
                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                  {creditBalance ?? "—"} credits available
                  {characterSlotSummary
                    ? ` • ${characterSlotSummary.used_slots}/${characterSlotSummary.total_slots} character slots used`
                    : ""}
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-aurora/30 bg-aurora/10 p-4">
                  <p className="text-sm text-slate-200">
                    Explore all plans and pricing. Create an account or sign in only when you are ready to start producing.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="rounded-lg bg-aurora px-4 py-2 text-sm font-semibold text-slate-950"
                      type="button"
                      onClick={() => router.push("/login?mode=register&next=%2F%3Fcredits%3D1")}
                    >
                      Create account
                    </button>
                    <button
                      className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200"
                      type="button"
                      onClick={() => router.push("/login?next=%2F%3Fcredits%3D1")}
                    >
                      Sign in
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="mt-4 flex-1 overflow-y-auto pr-1">
              {factoryAccessPlans.length > 0 ? (
                <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-white">Factory Mode Access</h3>
                    <p className="mt-1 text-sm text-slate-400">
                      Choose one-time access or a renewable subscription.
                    </p>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {factoryAccessPlans.map((plan) => {
                    const selected = selectedCreditPlanId === plan.id;
                    const planProviders = checkoutProvidersForPlan(plan);
                    return (
                      <button
                        key={plan.id}
                        type="button"
                        aria-label={`Select ${plan.name} access`}
                        aria-pressed={selected}
                        data-active-glow={selected ? "true" : undefined}
                        className={`rounded-xl border p-4 text-left transition ${
                          selected
                            ? "border-aurora/70 bg-aurora/15 ring-1 ring-aurora/40"
                            : "border-slate-800 bg-slate-900/50"
                        }`}
                        onClick={() => handleSelectCreditPlan(plan.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">{plan.name}</p>
                            <p className="mt-1 text-xs text-slate-400">{factoryAccessPlanLabel(plan)}</p>
                            <p className="mt-1 text-xs text-slate-500">${plan.price_usd}</p>
                            {plan.description ? (
                              <p className="mt-2 text-xs leading-5 text-slate-400">{plan.description}</p>
                            ) : null}
                            {planProviders.length > 0 ? (
                              <p className="mt-2 text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                {planProviders.map((provider) => billingProviderLabel(provider)).join(" / ")}
                              </p>
                            ) : null}
                          </div>
                          {selected ? (
                            <span className="rounded-full border border-aurora/40 bg-aurora/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-aurora">
                              Selected
                            </span>
                          ) : null}
                        </div>
                        <span className="mt-3 inline-flex rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-xs font-semibold text-aurora">
                          {factoryAccessPurchaseLabel(plan)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
            {creditPlansError ? (
              <p className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                {creditPlansError}
              </p>
            ) : null}
            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-white">Standard Mode Access</h3>
                  <p className="mt-1 text-sm text-slate-400">
                    Choose a standard credit pack for regular production work.
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {creditPlansLoading ? (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
                    Loading plans...
                  </div>
                ) : creditPurchasePlans.length > 0 ? (
                  creditPurchasePlans.map((plan) => {
                    const selected = selectedCreditPlanId === plan.id;
                    const planProviders = checkoutProvidersForPlan(plan);
                    return (
                      <div
                        key={plan.id}
                        role="button"
                        tabIndex={0}
                        aria-label={`Select ${plan.name} plan`}
                        aria-pressed={selected}
                        className={`rounded-xl border p-4 text-left transition ${
                          selected
                            ? "border-aurora/70 bg-aurora/15 ring-1 ring-aurora/40"
                            : "border-slate-800 bg-slate-900/50"
                        }`}
                        onClick={() => handleSelectCreditPlan(plan.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            handleSelectCreditPlan(plan.id);
                          }
                        }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">{plan.name}</p>
                            <p className="mt-1 text-xs text-slate-400">{plan.credits.toLocaleString()} credits</p>
                            <p className="mt-1 text-xs text-slate-500">${plan.price_usd}</p>
                            {planProviders.length > 0 ? (
                              <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                {planProviders.map((provider) => billingProviderLabel(provider)).join(" / ")}
                              </p>
                            ) : null}
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            {plan.popular ? (
                              <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-300">
                                Popular
                              </span>
                            ) : null}
                            {selected ? (
                              <span className="rounded-full border border-aurora/40 bg-aurora/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-aurora">
                                Selected
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <button
                          className="mt-3 w-full rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-xs font-semibold text-aurora disabled:opacity-60"
                          type="button"
                          disabled={purchaseLoadingPlan === plan.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleSelectCreditPlan(plan.id);
                          }}
                        >
                          Buy
                        </button>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
                    No purchasable plans are available right now.
                  </div>
                )}
              </div>
            </div>
            <div
              ref={paymentStepRef}
              className="mt-5 rounded-2xl border border-aurora/30 bg-slate-900/50 p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-lg font-semibold text-white">Payment options</h3>
                </div>
                <span className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-300">
                  {selectedCreditPlan ? selectedCreditPlan.name : "Select a plan"}
                </span>
              </div>
              {selectedCreditPlan ? (
                <>
                  <div className="mt-[3px] flex flex-col items-start gap-[3px]">
                    <div className="flex items-center gap-[3px]">
                      <span
                        className={`inline-flex h-[34px] w-[11.5rem] items-center justify-center rounded-full border px-3 text-xs font-semibold uppercase tracking-[0.18em] ${paymentProviderPillClasses(
                          selectedPurchaseProvider
                        )}`}
                      >
                        {paymentProviderLabel(selectedPurchaseProvider)}
                      </span>
                      <span className="text-xs uppercase tracking-[0.25em] text-slate-500">Default</span>
                    </div>
                  </div>
                  {purchaseProviderOptions.length > 0 ? (
                    <div className="mt-[3px] flex flex-col items-start gap-[3px]">
                      <div className="flex items-center gap-[3px]">
                        <button
                          type="button"
                          className={`inline-flex h-[34px] w-[11.5rem] items-center justify-center rounded-full border px-3 text-xs font-semibold uppercase tracking-[0.2em] transition ${
                          selectedPurchaseProvider === "paystack"
                            ? "border-blue-400/95 bg-slate-900/50 shadow-[0_0_0_1px_rgba(59,130,246,0.52),0_0_18px_rgba(59,130,246,0.3)]"
                            : "border-purple-300/95 bg-slate-900/50 shadow-[0_0_0_1px_rgba(168,85,247,0.48),0_0_18px_rgba(168,85,247,0.26)]"
                          }`}
                          aria-pressed={selectedPurchaseProvider === "paystack"}
                          onClick={() =>
                            handleSelectPurchaseProvider(
                              selectedPurchaseProvider === "paystack" ? "stripe" : "paystack"
                            )
                          }
                        >
                          {paymentProviderToggleText()}
                        </button>
                        <span className="text-xs uppercase tracking-[0.25em] text-slate-500">Provider</span>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs uppercase tracking-[0.25em] text-slate-500">
                      No live provider is configured yet. Fallback payment routes are available for testing.
                    </p>
                  )}
                  <button
                    className="mt-[3px] inline-flex h-[34px] w-[11.5rem] items-center justify-center rounded-lg border border-aurora/40 bg-aurora/10 px-3 text-sm font-semibold text-aurora disabled:opacity-60"
                    type="button"
                    disabled={purchaseLoadingPlan === selectedCreditPlan.id}
                    onClick={() => void handlePurchasePlan(selectedCreditPlan.id)}
                  >
                    {purchaseLoadingPlan === selectedCreditPlan.id ? "Processing..." : "Proceed to payment"}
                  </button>
                  <p className="mt-[3px] text-sm text-slate-300">
                    {selectedBillingPlanSummary(selectedCreditPlan)}
                  </p>
                </>
              ) : (
                <p className="mt-4 text-sm text-slate-400">
                  Select a plan above to unlock the payment step.
                </p>
              )}
            </div>
            {isAuthenticated ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-white">Recent receipts</h3>
                <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Transactions</span>
              </div>
              {billingReceiptsLoading ? (
                <p className="mt-3 text-sm text-slate-400">Loading receipts...</p>
              ) : billingReceiptsError ? (
                <p className="mt-3 text-sm text-rose-300">{billingReceiptsError}</p>
              ) : (
                <>
                  {billingReceiptsMessage ? (
                    <p className="mt-3 text-sm text-emerald-300">{billingReceiptsMessage}</p>
                  ) : null}
                  {billingReceipts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {billingReceipts.map((receipt, index) => {
                    const providerLabel = receipt.provider === "paystack"
                      ? "Paystack / MoMo"
                      : receipt.provider === "stripe"
                        ? "Stripe"
                        : "Payment";
                    const receiptTitle =
                      receipt.plan_id === "moderate"
                        ? "Moderate"
                        : receipt.plan_id === "pro"
                          ? "Pro"
                          : receipt.plan_id === "studio"
                            ? "Studio"
                            : receipt.plan_id ?? "Receipt";
                    return (
                      <div
                        key={`${receipt.receipt_id}:${receipt.action ?? "billing"}:${receipt.reference_id ?? receipt.created_at}:${index}`}
                        className="rounded-xl border border-slate-800 bg-slate-900/50 px-3 py-2 transition hover:border-slate-700 hover:bg-slate-900/70"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-[3px]">
                              <p className="text-sm font-semibold text-white">{receiptTitle}</p>
                              <span
                                className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${receiptProviderPillClasses(receipt.provider)}`}
                              >
                                {providerLabel}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-slate-400">{receipt.amount.toLocaleString()} credits</p>
                          </div>
                          <div className="flex flex-col items-end gap-2 text-right text-[10px] uppercase tracking-[0.18em] text-slate-500">
                            <p>{new Date(receipt.created_at).toLocaleString()}</p>
                            {receipt.reference_id ? (
                              <p className="font-mono text-slate-400 normal-case tracking-normal">
                                {receipt.reference_id}
                              </p>
                            ) : null}
                            <button
                              className="rounded-full border border-slate-700 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300 transition hover:border-rose-400/40 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                              type="button"
                              disabled={billingReceiptDeleteId === receipt.receipt_id}
                              onClick={() => void handleDeleteReceipt(receipt.receipt_id)}
                            >
                              {billingReceiptDeleteId === receipt.receipt_id ? "Removing..." : "Remove"}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                  ) : (
                    <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                      No receipts yet. Completed purchases will appear here.
                    </p>
                  )}
                </>
              )}
            </div>
            ) : null}
            </div>
            {purchaseStatus ? (
              <p className="mt-3 text-xs text-emerald-300">{purchaseStatus}</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
