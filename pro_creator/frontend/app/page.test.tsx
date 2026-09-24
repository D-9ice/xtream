import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../lib/api";
import HomePage from "./page";

const mockState = vi.hoisted(() => ({
  defaults: {
    project: {
      project_id: "project-1",
      title: "Moonlight Rescue",
      topic: "Moonlight Rescue",
      status: "script_generated",
      idea_prompt: "A rescue mission under moonlight.",
      genre: "Adventure",
      target_duration_minutes: 4,
      workflow_state: "script_generated",
      script_draft: "Scene 1: The crew spots the signal.",
      script_approved: null,
      script_approved_at: null,
      character_package_approved: false,
      character_package_approved_at: null,
      selected_character_ids: [],
      production_job_id: null,
      final_video_url: null,
      created_at: "2026-03-22T00:00:00",
      updated_at: "2026-03-22T00:00:00",
    },
    characters: {
      library: [],
      selected_character_ids: [],
      selected: [],
      approved_character_ids: [],
      approved_at: null,
    },
    library: {
      characters: [],
      scripts: [],
      videos: [],
    },
    summary: {
      project_id: "project-1",
      workflow_state: "script_generated",
      script_ready: false,
      characters_ready: false,
      estimated_credits: 20,
      current_credit_balance: 120,
      target_duration_minutes: 4,
      selected_characters: [],
      final_video_url: null,
    },
    productionStatus: {
      project_id: "project-1",
      workflow_state: "script_generated",
      production_job_id: null,
      queue_status: null,
      queue_attempts: 0,
      queue_max_attempts: 0,
      last_error: null,
      can_retry: false,
      final_video_url: null,
    },
    credits: {
      email: "owner@example.com",
      plan_name: "pro",
      status: "active",
      credits_balance: 120,
      credits_reserved: 0,
      credits_used_total: 0,
      renewal_date: null,
      extra_character_slots: 0,
      owner_mode_enabled: false,
      factory_mode_status: "inactive",
      factory_mode_access: "none",
      factory_mode_renewal_date: null,
      factory_mode_purchased_at: null,
      character_slots: {
        base_slots: 10,
        extra_slots: 0,
        total_slots: 10,
        used_slots: 2,
        remaining_slots: 8,
        addon_pack_size: 5,
        addon_pack_cost_credits: 50,
        is_full: false,
      },
    },
    social: {
      connections: [],
      jobs: [],
    },
    community: {
      posts: [],
    },
    billing: {
      receipts: [],
      transactionRecords: [],
    },
  },
  project: {} as Record<string, unknown>,
  characters: {} as Record<string, unknown>,
  library: {} as Record<string, unknown>,
  summary: {} as Record<string, unknown>,
  productionStatus: {} as Record<string, unknown>,
  credits: {} as Record<string, unknown>,
  social: {} as Record<string, unknown>,
  community: {} as Record<string, unknown>,
  billing: {} as Record<string, unknown>,
}));

const mockNavigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  router: {
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  },
}));

const mockSearchParams = vi.hoisted(() => new URLSearchParams());

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function resetMockState() {
  mockState.project = clone(mockState.defaults.project);
  mockState.characters = clone(mockState.defaults.characters);
  mockState.library = clone(mockState.defaults.library);
  mockState.summary = clone(mockState.defaults.summary);
  mockState.productionStatus = clone(mockState.defaults.productionStatus);
  mockState.credits = clone(mockState.defaults.credits);
  mockState.social = clone(mockState.defaults.social);
  mockState.community = clone(mockState.defaults.community);
  mockState.billing = clone(mockState.defaults.billing);
}

function navButton(label: RegExp): HTMLElement {
  return screen.getAllByRole("button", { name: label })[0];
}

vi.mock("next/navigation", () => ({
  useRouter: () => mockNavigation.router,
  useSearchParams: () => mockSearchParams,
}));

vi.mock("../lib/api", () => ({
  fetchWorkflowProjects: vi.fn(async () => [clone(mockState.project)]),
  fetchWorkflowProject: vi.fn(async () => clone(mockState.project)),
  fetchWorkflowCharacters: vi.fn(async () => clone(mockState.characters)),
  fetchWorkflowLibrary: vi.fn(async () => clone(mockState.library)),
  fetchWorkflowProductionSummary: vi.fn(async () => clone(mockState.summary)),
  fetchWorkflowProductionStatus: vi.fn(async () => clone(mockState.productionStatus)),
  fetchMyCredits: vi.fn(async () => clone(mockState.credits)),
  fetchBillingReceipts: vi.fn(async () => ({
    items: clone(mockState.billing.receipts),
  })),
  fetchBillingTransactionRecords: vi.fn(async () => ({
    items: clone(mockState.billing.transactionRecords ?? []),
  })),
  deleteBillingReceipt: vi.fn(async (receiptId: number) => {
    mockState.billing.receipts = mockState.billing.receipts.filter(
      (receipt: { receipt_id: number }) => receipt.receipt_id !== receiptId
    );
    return { deleted: true, receipt_id: receiptId, deleted_permanently: true };
  }),
  deleteWorkflowProjects: vi.fn(async () => {
    mockState.project = clone(mockState.defaults.project);
    mockState.library = clone(mockState.defaults.library);
    return {
      deleted_count: 1,
      deleted_ids: ["project-1"],
    };
  }),
  fetchSocialConnections: vi.fn(async () => ({
    items: clone(mockState.social.connections),
  })),
  fetchSocialPublishJobs: vi.fn(async () => ({
    items: clone(mockState.social.jobs),
  })),
  fetchCommunityPosts: vi.fn(async () => ({
    items: clone(mockState.community.posts),
  })),
  createCommunityPost: vi.fn(async (payload: { subject: string; message: string }) => {
    const post = {
      post_id: `community-${mockState.community.posts.length + 1}`,
      subject: payload.subject,
      message: payload.message,
      author_label: "Owner",
      author_email: "owner@example.com",
      applause_count: 0,
      created_at: "2026-04-06T00:00:00Z",
    };
    mockState.community.posts = [post, ...mockState.community.posts];
    return clone(post);
  }),
  applaudCommunityPost: vi.fn(async (postId: string) => {
    mockState.community.posts = mockState.community.posts.map((post) =>
      post.post_id === postId ? { ...post, applause_count: (post.applause_count ?? 0) + 1 } : post
    );
    return clone(mockState.community.posts.find((post) => post.post_id === postId));
  }),
  submitWorkflowFeedback: vi.fn(async (payload: { subject: string; message: string; page?: string | null; project_id?: string | null }) => ({
    feedback_id: "feedback-1",
    subject: payload.subject,
    page: payload.page ?? null,
    project_id: payload.project_id ?? null,
    email_sent: true,
    created_at: "2026-04-04T00:00:00Z",
  })),
  createWorkflowProject: vi.fn(),
  autoCreateWorkflowProject: vi.fn(async (payload: { title: string; duration_minutes?: number }) => {
    const duration = payload.duration_minutes ?? 10;
    const project = {
      ...clone(mockState.defaults.project),
      project_id: "project-auto",
      title: payload.title,
      topic: payload.title,
      status: "video_completed",
      workflow_state: "video_completed",
      script_draft: "Scene 1: Auto-created opening.",
      script_approved: "Scene 1: Auto-created opening.",
      script_approved_at: "2026-04-03T00:00:00",
      character_package_approved: true,
      character_package_approved_at: "2026-04-03T00:00:00",
      selected_character_ids: ["character-1", "character-2"],
      production_job_id: "job-auto",
      final_video_url: "https://example.test/auto-created.mp4",
      updated_at: "2026-04-03T00:00:00",
    };
    mockState.project = clone(project);
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      project_id: project.project_id,
      workflow_state: "video_completed",
      script_ready: true,
      characters_ready: true,
      final_video_url: project.final_video_url,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      project_id: project.project_id,
      workflow_state: "video_completed",
      production_job_id: "job-auto",
      queue_status: "complete",
      final_video_url: project.final_video_url,
    };
    mockState.characters = {
      library: [
        {
          character_id: "character-1",
          name: "Auto Title Lead",
          role_type: "main",
          description: "Primary character for the auto-created project.",
          visual_prompt_base: "Auto Title Lead",
          negative_prompt_base: "blurry",
          consistency_seed: "seed-1",
          identity_hash: "hash-1",
          lock_identity: true,
          reference_image_url: null,
          reference_image_urls: [],
          canonical_image_url: null,
          personality_traits: [],
          voice_profile: "default",
          created_at: "2026-04-03T00:00:00",
          updated_at: "2026-04-03T00:00:00",
        },
        {
          character_id: "character-2",
          name: "Auto Title Support",
          role_type: "supporting",
          description: "Supporting character for the auto-created project.",
          visual_prompt_base: "Auto Title Support",
          negative_prompt_base: "blurry",
          consistency_seed: "seed-2",
          identity_hash: "hash-2",
          lock_identity: true,
          reference_image_url: null,
          reference_image_urls: [],
          canonical_image_url: null,
          personality_traits: [],
          voice_profile: "default",
          created_at: "2026-04-03T00:00:00",
          updated_at: "2026-04-03T00:00:00",
        },
      ],
      selected_character_ids: ["character-1", "character-2"],
      selected: [],
      approved_character_ids: ["character-1", "character-2"],
      approved_at: "2026-04-03T00:00:00",
    };
    mockState.library = {
      characters: clone(mockState.characters.library),
      scripts: [clone(project)],
      videos: [clone(project)],
    };
    return {
      project: clone(project),
      status: clone(mockState.productionStatus),
      video_path: project.final_video_url,
      requested_duration_minutes: duration,
      applied_duration_minutes: duration,
      max_affordable_duration_minutes: 120,
      estimated_credits: 20,
    };
  }),
  updateWorkflowProject: vi.fn(),
  archiveWorkflowProject: vi.fn(),
  duplicateWorkflowProject: vi.fn(),
  generateWorkflowScript: vi.fn(),
  approveWorkflowScript: vi.fn(),
  regenerateWorkflowScript: vi.fn(),
  updateWorkflowScript: vi.fn(),
  selectWorkflowCharacters: vi.fn(),
  createWorkflowCharacter: vi.fn(),
  generateWorkflowCharacter: vi.fn(),
  uploadWorkflowCharacter: vi.fn(),
  createLibraryCharacter: vi.fn(async (payload: { name: string; role_type?: string; description: string }) => {
    const character = {
      character_id: `library-${mockState.library.characters.length + 1}`,
      name: payload.name,
      role_type: payload.role_type ?? "supporting",
      description: payload.description,
      visual_prompt_base: payload.name,
      negative_prompt_base: "blurry",
      consistency_seed: `seed-${mockState.library.characters.length + 1}`,
      identity_hash: `hash-${mockState.library.characters.length + 1}`,
      lock_identity: true,
      reference_image_url: null,
      reference_image_urls: [],
      canonical_image_url: null,
      personality_traits: [],
      voice_profile: "default",
      created_at: "2026-04-09T00:00:00",
      updated_at: "2026-04-09T00:00:00",
    };
    mockState.library = {
      ...mockState.library,
      characters: [character, ...mockState.library.characters],
    };
    return clone(mockState.library);
  }),
  generateLibraryCharacter: vi.fn(async (payload: { name: string; role_type?: string; description: string }) => {
    const character = {
      character_id: `library-${mockState.library.characters.length + 1}`,
      name: payload.name,
      role_type: payload.role_type ?? "supporting",
      description: payload.description,
      visual_prompt_base: payload.name,
      negative_prompt_base: "blurry",
      consistency_seed: `seed-${mockState.library.characters.length + 1}`,
      identity_hash: `hash-${mockState.library.characters.length + 1}`,
      lock_identity: true,
      reference_image_url: null,
      reference_image_urls: [],
      canonical_image_url: null,
      personality_traits: [],
      voice_profile: "default",
      created_at: "2026-04-09T00:00:00",
      updated_at: "2026-04-09T00:00:00",
    };
    mockState.library = {
      ...mockState.library,
      characters: [character, ...mockState.library.characters],
    };
    return clone(mockState.library);
  }),
  uploadLibraryCharacter: vi.fn(async (payload: { file: File; name: string; role_type?: string; description?: string }) => {
    const character = {
      character_id: `library-${mockState.library.characters.length + 1}`,
      name: payload.name,
      role_type: payload.role_type ?? "supporting",
      description: payload.description ?? "",
      visual_prompt_base: payload.name,
      negative_prompt_base: "blurry",
      consistency_seed: `seed-${mockState.library.characters.length + 1}`,
      identity_hash: `hash-${mockState.library.characters.length + 1}`,
      lock_identity: true,
      reference_image_url: "https://example.test/reference.png",
      reference_image_urls: ["https://example.test/reference.png"],
      canonical_image_url: null,
      personality_traits: [],
      voice_profile: "default",
      created_at: "2026-04-09T00:00:00",
      updated_at: "2026-04-09T00:00:00",
    };
    mockState.library = {
      ...mockState.library,
      characters: [character, ...mockState.library.characters],
    };
    return clone(mockState.library);
  }),
  purchaseCharacterSlotPack: vi.fn(async () => clone(mockState.credits)),
  approveWorkflowCharacters: vi.fn(),
  startWorkflowProduction: vi.fn(async () => ({
    project: clone(mockState.project),
    status: clone(mockState.productionStatus),
    video_path: null,
  })),
  retryWorkflowProduction: vi.fn(async () => clone(mockState.productionStatus)),
  fetchCreditPlans: vi.fn(async () => ({
    plans: [
      {
        id: "moderate",
        name: "Moderate",
        kind: "credits",
        credits: 500,
        price_usd: 15,
        popular: false,
        stripe_price_id: "price_moderate",
        checkout_providers: ["stripe", "paystack"],
        checkout_enabled: true,
      },
      {
        id: "pro",
        name: "Pro",
        kind: "credits",
        credits: 2000,
        price_usd: 49,
        popular: true,
        stripe_price_id: "price_pro",
        checkout_providers: ["stripe", "paystack"],
        checkout_enabled: true,
      },
      {
        id: "studio",
        name: "Studio",
        kind: "credits",
        credits: 6000,
        price_usd: 119,
        popular: false,
        stripe_price_id: "price_studio",
        checkout_providers: ["stripe", "paystack"],
        checkout_enabled: true,
      },
      {
        id: "factory_one_time",
        name: "Factory Mode One-Time",
        kind: "factory_access",
        access_mode: "one_time",
        access_days: null,
        description: "Unlimited autonomous production access without expiration.",
        credits: 0,
        price_usd: 149,
        popular: false,
        stripe_price_id: "price_factory_one_time",
        checkout_providers: ["stripe", "paystack"],
        checkout_enabled: true,
      },
      {
        id: "factory_subscription",
        name: "Factory Mode Subscription",
        kind: "factory_access",
        access_mode: "subscription",
        access_days: 30,
        description: "Autonomous production access that renews every billing cycle.",
        credits: 0,
        price_usd: 39,
        popular: false,
        stripe_price_id: "price_factory_subscription",
        checkout_providers: ["stripe", "paystack"],
        checkout_enabled: true,
      },
    ],
  })),
  createStripeCheckoutSession: vi.fn(async (payload: { plan_id: string; provider?: string }) => ({
    session_id: "checkout-session",
    checkout_url: "https://example.test/checkout",
    provider: payload.provider ?? "stripe",
  })),
  saveSocialConnection: vi.fn(async (payload: {
    connection_id?: string | null;
    platform: string;
    account_label: string;
    account_identifier?: string | null;
    access_token: string;
    access_token_secret?: string | null;
    refresh_token?: string | null;
    client_key?: string | null;
    client_secret?: string | null;
    token_expires_at?: string | null;
    scopes?: string[];
    metadata?: Record<string, string>;
    enabled?: boolean;
  }) => {
    const connection = {
      connection_id: payload.connection_id ?? "connection-1",
      platform: payload.platform,
      account_label: payload.account_label,
      account_identifier: payload.account_identifier ?? null,
      scopes: payload.scopes ?? [],
      metadata: payload.metadata ?? {},
      enabled: payload.enabled ?? true,
      token_expires_at: payload.token_expires_at ?? null,
      created_at: "2026-04-03T00:00:00",
      updated_at: "2026-04-03T00:00:00",
    };
    mockState.social.connections = [connection];
    return clone(connection);
  }),
  deleteSocialConnection: vi.fn(async (connectionId: string) => {
    mockState.social.connections = mockState.social.connections.filter(
      (connection: { connection_id: string }) => connection.connection_id !== connectionId
    );
    return { deleted: true };
  }),
  publishSocialVideos: vi.fn(async (payload: { project_id: string; connection_ids?: string[]; message?: string | null; title?: string | null }) => {
    const selectedIds =
      payload.connection_ids && payload.connection_ids.length > 0
        ? payload.connection_ids
        : mockState.social.connections.map((connection: { connection_id: string }) => connection.connection_id);
    const items = selectedIds.map((connectionId: string) => ({
      job_id: `job-${connectionId}`,
      project_id: payload.project_id,
      connection_id: connectionId,
      platform:
        mockState.social.connections.find((connection: { connection_id: string }) => connection.connection_id === connectionId)?.platform ??
        "youtube",
      status: "complete",
      remote_post_id: `post-${connectionId}`,
      published_url: `https://example.test/published/${connectionId}`,
      error_message: null,
      created_at: "2026-04-03T00:00:00",
      updated_at: "2026-04-03T00:00:00",
      published_at: "2026-04-03T00:00:00",
    }));
    mockState.social.jobs = items;
    return { items };
  }),
  exportPreset: vi.fn(async () => ({ export_path: "https://example.test/export.mp4" })),
  exportBatch: vi.fn(async () => ({ exports: ["https://example.test/export-batch.mp4"] })),
  fetchExportStatus: vi.fn(async () => ({
    project_id: "project-1",
    exports: [],
  })),
}));

describe("Workflow home page", () => {
  beforeEach(() => {
    resetMockState();
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.clearAllMocks();
    mockNavigation.push.mockReset();
    mockNavigation.replace.mockReset();
    mockNavigation.router.push.mockReset();
    mockNavigation.router.replace.mockReset();
    mockNavigation.router.prefetch.mockReset();
    mockNavigation.router.back.mockReset();
    mockNavigation.router.forward.mockReset();
    mockNavigation.router.refresh.mockReset();
    vi.useRealTimers();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("shows the simplified nine-item navigation plus feedback", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Overview/i)).toBeInTheDocument();
    });

    ["Auto-Create", "Download", "Factory Mode", "Library", "Manual-Create", "Overview", "Playback", "Projects", "Publish", "Transaction Records", "ProCreators"].forEach((label) => {
      expect(navButton(new RegExp(label, "i"))).toBeInTheDocument();
    });
    expect(navButton(/User Feedback/i)).toBeInTheDocument();

    expect(navButton(/Auto-Create/i)).toHaveAttribute("data-active-glow", "true");
    expect(navButton(/Auto-Create/i)).toHaveClass("border-white/95");

    ["Engines", "Automation", "Orchestration", "Logs"].forEach((label) => {
      expect(screen.queryByRole("button", { name: new RegExp(label, "i") })).toBeNull();
    });
  });

  it("routes to Factory Mode when the nav item is selected", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Factory Mode/i)).toBeInTheDocument();
    });

    const factoryTab = navButton(/Factory Mode/i);
    fireEvent.click(factoryTab);

    await waitFor(() => {
      expect(mockNavigation.router.push).toHaveBeenCalledWith("/factory-mode");
    });
  });

  it("routes to Factory Mode when Series Video Maker is selected", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Auto-Create/i));

    const genreSelect = await screen.findByLabelText(/Genre/i);
    fireEvent.change(genreSelect, {
      target: { value: "Series Video Maker (Factory Mode Only)" },
    });

    await waitFor(() => {
      expect(mockNavigation.router.push).toHaveBeenCalledWith("/factory-mode");
    });
  });

  it("runs the Auto-Create flow from a single title input", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Auto-Create/i));
    await waitFor(() => {
      expect(screen.getByText(/Waiting for process/i)).toBeInTheDocument();
    });

    fireEvent.change(await screen.findByLabelText(/Video Title/i), {
      target: { value: "Skyline Rescue" },
    });
    expect(screen.getByRole("option", { name: /3D Anime/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Cartoons/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Detective \/ Investigative/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /^Real Events$/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Religion/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Series Video Maker \(Factory Mode Only\)/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /True Story/i })).toBeInTheDocument();
    expect(
      screen.getAllByRole("option").map((option) => option.textContent?.trim())
    ).toEqual([
      "3D Anime",
      "Action",
      "Adventure",
      "African Drama",
      "Cartoons",
      "Comedy",
      "Detective / Investigative",
      "Documentary",
      "Drama",
      "Fantasy",
      "Historical",
      "Horror",
      "Mystery",
      "PodCast",
      "Real Events",
      "Religion",
      "Romance",
      "Sci-Fi",
      "Series Video Maker (Factory Mode Only)",
      "SitComs",
      "Thriller",
      "True Story",
      "Wildlife/Animals",
    ]);
    fireEvent.change(screen.getByLabelText(/Genre/i), {
      target: { value: "True Story" },
    });
    expect(screen.getByText(/True Story uses factual research mode\./i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Duration/i), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));

    await waitFor(() => {
      expect(api.autoCreateWorkflowProject).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Skyline Rescue",
          duration_minutes: 45,
          genre: "True Story",
          short_description: undefined,
          start_credits: undefined,
          end_credits: undefined,
          custom_characters: [],
        })
      );
    });

    expect((await screen.findAllByText(/VIDEO READY/i)).length).toBeGreaterThan(0);
  }, 30000);

  it("passes optional auto-create studio controls and skips AI cast generation when custom characters are provided", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Auto-Create/i));

    fireEvent.change(await screen.findByLabelText(/Video Title/i), {
      target: { value: "Studio Premiere" },
    });
    fireEvent.change(screen.getByLabelText(/Short Description/i), {
      target: { value: "A compact studio-style launch piece." },
    });
    fireEvent.change(screen.getByLabelText(/Genre/i), {
      target: { value: "Drama" },
    });
    fireEvent.change(screen.getByLabelText(/^Start Credits/i), {
      target: { value: "Starring\nLead Actor\nDirected by X'tream" },
    });
    fireEvent.change(screen.getByLabelText(/^End Credits/i), {
      target: { value: "Thanks for watching\nProduced by X'tream" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Add Character/i }));

    fireEvent.change(screen.getByLabelText(/Character Name/i), {
      target: { value: "Ava Nova" },
    });
    fireEvent.change(screen.getByLabelText(/Role Type/i), {
      target: { value: "main" },
    });
    fireEvent.change(screen.getByLabelText(/^Description$/i), {
      target: { value: "Confident producer leading the feature launch." },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));

    await waitFor(() => {
      expect(api.autoCreateWorkflowProject).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Studio Premiere",
          duration_minutes: 10,
          genre: "Drama",
          short_description: "A compact studio-style launch piece.",
          start_credits: "Starring\nLead Actor\nDirected by X'tream",
          end_credits: "Thanks for watching\nProduced by X'tream",
          custom_characters: [
            {
              name: "Ava Nova",
              role_type: "main",
              description: "Confident producer leading the feature launch.",
            },
          ],
        })
      );
    });
  }, 30000);

  it("keeps social linking out of the auto-create surface", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Auto-Create/i));

    expect(screen.queryByText(/Connect a personal platform/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^YouTube$/i })).not.toBeInTheDocument();
  }, 20000);

  it("keeps future workflow steps disabled until earlier approvals exist", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Review Script/i })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Step 2 Review Script/i })).toBeEnabled();
    });

    expect(screen.getByRole("button", { name: /Step 1 Story Request/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Step 3 Choose Characters/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Step 4 Produce Video/i })).toBeDisabled();
  }, 20000);

  it("shows clear guided warnings before later workflow gates unlock", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(
      await screen.findByText(/Approve the script to unlock character selection/i, {}, { timeout: 5000 })
    ).toBeInTheDocument();

    expect(screen.getByText(/Step: Review Script/i)).toBeInTheDocument();
  }, 20000);

  it("shows explicit per-step status banners inside the create flow", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    await waitFor(() => {
      expect(screen.getAllByText(/Review required/i).length).toBeGreaterThan(0);
    }, { timeout: 15000 });

    expect(screen.getByText(/Review required/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting on Step 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting on Step 3/i)).toBeInTheDocument();
  });

  it("shows the current script draft in the review stage", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    const scriptEditor = await screen.findByDisplayValue(
      /Scene 1: The crew spots the signal\./i,
      {},
      { timeout: 5000 }
    );

    expect(scriptEditor).toBeEnabled();
    expect(screen.getAllByText(/Review Script/i).length).toBeGreaterThan(0);
  });

  it("shows guided navigation controls between unlocked create stages", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(await screen.findByText(/Step: Review Script/i, {}, { timeout: 5000 })).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Go to Script Review/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Back to Story Request/i })).toBeInTheDocument();
  });

  it("shows a mobile-friendly quick snapshot inside the create flow", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(await screen.findByText(/Quick Snapshot/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Step/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Next$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Cast$/i).length).toBeGreaterThan(0);
  }, 15000);

  it("shows a current-step jump action in the project summary", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });
    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(await screen.findByText(/Step: Review Script/i, {}, { timeout: 15000 })).toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: /Jump/i }, { timeout: 15000 })).length).toBeGreaterThan(0);
  }, 20000);

  it("opens the credit purchase panel from the top-right badge", async () => {
    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    expect(await screen.findByRole("dialog", { name: /Credit purchase panel/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.fetchCreditPlans).toHaveBeenCalled();
    });

    const proCard = screen.getByRole("button", { name: /Select Pro plan/i });
    fireEvent.click(proCard);
    expect(proCard).toHaveAttribute("aria-pressed", "true");

    const studioCard = screen.getByRole("button", { name: /Select Studio plan/i });
    fireEvent.click(studioCard);
    expect(studioCard).toHaveAttribute("aria-pressed", "true");
    expect(proCard).toHaveAttribute("aria-pressed", "false");
  }, 20000);

  it("shows factory mode access cards in the credit purchase panel", async () => {
    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    expect(await screen.findByText(/Factory Mode Access/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Select Factory Mode One-Time access/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Select Factory Mode Subscription access/i })).toBeInTheDocument();
    expect(screen.getByText(/^Unlock$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Subscribe$/i)).toBeInTheDocument();
  }, 20000);

  it("allows the user to select Factory Mode access in the credit purchase panel", async () => {
    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    const factoryOneTimeCard = await screen.findByRole("button", {
      name: /Select Factory Mode One-Time access/i,
    });
    fireEvent.click(factoryOneTimeCard);

    expect(factoryOneTimeCard).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("$149")).toBeInTheDocument();
  }, 20000);

  it("shows recent receipts inside the credit purchase panel", async () => {
    mockState.billing.receipts = [
      {
        receipt_id: 101,
        created_at: "2026-04-04T10:00:00Z",
        kind: "grant",
        action: "billing.purchase.paystack",
        amount: 2000,
        reason: "paystack purchase pro",
        reference_id: "ps_ref_1234",
        provider: "paystack",
        balance_after: 2120,
        reserved_after: 0,
        plan_id: "pro",
        metadata: {
          tenant_id: "billing-default",
        },
      },
    ];

    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    expect(await screen.findByText(/Recent receipts/i)).toBeInTheDocument();
    expect(await screen.findByText(/^Paystack \/ MoMo$/i, { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText(/ps_ref_1234/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Remove$/i }));
    await waitFor(() => {
      expect(vi.mocked(api.deleteBillingReceipt)).toHaveBeenCalledWith(101);
    });
    expect(screen.queryByText(/ps_ref_1234/i)).toBeNull();

    await waitFor(() => {
      expect(vi.mocked(api.fetchBillingReceipts)).toHaveBeenCalled();
    });
  }, 20000);

  it("shows immutable transaction records in the sidebar tab", async () => {
    mockState.billing.transactionRecords = [
      {
        record_id: 201,
        created_at: "2026-04-04T11:00:00Z",
        kind: "consume",
        action: "manual_consume",
        amount: 10,
        reason: "test spend",
        reference_id: "tx_ref_201",
        provider: null,
        balance_after: 110,
        reserved_after: 0,
        metadata: {},
      },
    ];

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Transaction Records/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Transaction Records/i));

    expect(await screen.findByRole("heading", { name: /Immutable ledger copy/i })).toBeInTheDocument();
    expect(await screen.findByText(/test spend/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove$/i })).toBeNull();
  }, 20000);

  it("lets the user switch the credit checkout provider to Paystack", async () => {
    const dateTimeSpy = vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "America/New_York" }),
    } as unknown as Intl.DateTimeFormat);

    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    const buyButtons = await screen.findAllByRole("button", { name: /^Buy$/i });
    fireEvent.click(buyButtons[0]);

    const paystackToggle = await screen.findByRole("button", { name: /PAYSTACK \/ STRIPE/i });
    fireEvent.click(paystackToggle);
    expect(paystackToggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/^Paystack \/ MoMo$/i, { selector: "span" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Proceed to payment/i }));

    await waitFor(() => {
      expect(vi.mocked(api.createStripeCheckoutSession)).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_id: expect.any(String),
          provider: "paystack",
        })
      );
    });

    dateTimeSpy.mockRestore();
  }, 20000);

  it("falls back to visible Stripe and Paystack / MoMo payment routes when no provider is configured", async () => {
    vi.mocked(api.fetchCreditPlans).mockResolvedValueOnce({
      plans: [
        {
          id: "moderate",
          name: "Moderate",
          credits: 500,
          price_usd: 15,
          popular: false,
          stripe_price_id: null,
          checkout_providers: [],
          checkout_enabled: false,
        },
      ],
    });

    const dateTimeSpy = vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "Africa/Accra" }),
    } as unknown as Intl.DateTimeFormat);

    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    const buyButtons = await screen.findAllByRole("button", { name: /^Buy$/i });
    fireEvent.click(buyButtons[0]);

    const providerToggle = await screen.findByRole("button", { name: /PAYSTACK \/ STRIPE/i });

    await waitFor(() => {
      expect(providerToggle).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByText(/^Paystack \/ MoMo$/i, { selector: "span" })).toBeInTheDocument();

    fireEvent.click(providerToggle);
    expect(providerToggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.getAllByText(/^Stripe$/i, { selector: "span" })[0]).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Proceed to payment/i }));

    await waitFor(() => {
      expect(vi.mocked(api.createStripeCheckoutSession)).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_id: "moderate",
          provider: "stripe",
        })
      );
    });

    dateTimeSpy.mockRestore();
  }, 20000);

  it("defaults the credit checkout provider to Paystack for Ghana-based browsers", async () => {
    const dateTimeSpy = vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "Africa/Accra" }),
    } as unknown as Intl.DateTimeFormat);

    render(<HomePage />);

    const creditButton = await screen.findByRole("button", {
      name: /Credits & Plans/i,
    });
    fireEvent.click(creditButton);

    const buyButtons = await screen.findAllByRole("button", { name: /^Buy$/i });
    fireEvent.click(buyButtons[0]);
    const paystackToggle = await screen.findByRole("button", { name: /PAYSTACK \/ STRIPE/i });
    await waitFor(() => {
      expect(paystackToggle).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByText(/^Paystack \/ MoMo$/i, { selector: "span" })).toBeInTheDocument();

    dateTimeSpy.mockRestore();
  }, 20000);

  it("shows a separate feedback tab at the bottom and submits feedback there", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    const feedbackTab = navButton(/User Feedback/i);
    fireEvent.click(feedbackTab);

    expect(await screen.findByRole("heading", { name: /User Feedback/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Subject/i), {
      target: { value: "Feature suggestion" },
    });
    fireEvent.change(screen.getByLabelText(/Message/i), {
      target: { value: "Please simplify the publish preview." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Submit/i }));

    await waitFor(() => {
      expect(vi.mocked(api.submitWorkflowFeedback)).toHaveBeenCalledWith({
        subject: "Feature suggestion",
        message: "Please simplify the publish preview.",
        page: "feedback",
        project_id: "project-1",
      });
    });

    expect(await screen.findByText(/Feedback sent\./i)).toBeInTheDocument();
  }, 20000);

  it("shows the ProCreators community tab and posts a discussion", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    const communityTab = navButton(/ProCreators/i);
    fireEvent.click(communityTab);

    expect(await screen.findByRole("heading", { name: /ProCreators/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Topic/i), {
      target: { value: "Feature idea" },
    });
    fireEvent.change(screen.getByLabelText(/Message/i), {
      target: { value: "Let's add a rotating community showcase." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Post$/i }));

    await waitFor(() => {
      expect(vi.mocked(api.createCommunityPost)).toHaveBeenCalledWith({
        subject: "Feature idea",
        message: "Let's add a rotating community showcase.",
      });
    });

    expect(await screen.findByText(/Posted to ProCreators\./i)).toBeInTheDocument();
  }, 20000);

  it("lets the user applaud a community post", async () => {
    mockState.community.posts = [
      {
        post_id: "community-1",
        subject: "Feature idea",
        message: "Let's add a creator showcase and lightweight discussion board.",
        author_label: "Owner",
        author_email: "owner@example.com",
        applause_count: 0,
        created_at: "2026-04-06T00:00:00Z",
      },
    ];

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/ProCreators/i));

    expect(await screen.findByText(/0 applause/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Applaud$/i }));

    await waitFor(() => {
      expect(vi.mocked(api.applaudCommunityPost)).toHaveBeenCalledWith("community-1");
    });

    expect(await screen.findByText(/1 applause/i)).toBeInTheDocument();
  }, 20000);

  it("shows pinned community topics and lets a user reuse one as the topic", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Auto-Create/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/ProCreators/i));

    expect(await screen.findByText(/Pinned topics/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Feature ideas/i }));

    expect(screen.getByLabelText(/Topic/i)).toHaveValue("Feature ideas");
  }, 20000);

  it("polls production status while a video is queued and refreshes to completed", async () => {
    vi.useFakeTimers();

    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_queued",
      status: "production_queued",
      script_approved: "Approved script",
      character_package_approved: true,
      selected_character_ids: ["char-1"],
      production_job_id: "42",
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_queued",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_queued",
      production_job_id: "42",
      queue_status: "queued",
      queue_max_attempts: 1,
    };

    let statusCalls = 0;
    vi.mocked(api.fetchWorkflowProductionStatus).mockImplementation(async () => {
      statusCalls += 1;
      if (statusCalls > 1) {
        mockState.project = {
          ...mockState.project,
          workflow_state: "video_completed",
          status: "video_completed",
          final_video_url: "https://example.test/final-video.mp4",
        };
        mockState.summary = {
          ...mockState.summary,
          workflow_state: "video_completed",
          final_video_url: "https://example.test/final-video.mp4",
        };
        mockState.productionStatus = {
          ...mockState.productionStatus,
          workflow_state: "video_completed",
          queue_status: "complete",
          queue_attempts: 1,
          final_video_url: "https://example.test/final-video.mp4",
        };
      }
      return clone(mockState.productionStatus);
    });

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getAllByText(/Queued for production/i).length).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getAllByText(/Video completed/i).length).toBeGreaterThan(0);

    expect(vi.mocked(api.fetchWorkflowProductionStatus).mock.calls.length).toBeGreaterThan(1);
  }, 20000);

  it("shows retry controls for failed production and requeues on demand", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_failed",
      status: "production_failed",
      script_approved: "Approved script",
      character_package_approved: true,
      selected_character_ids: ["char-1"],
      production_job_id: "51",
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_failed",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_failed",
      production_job_id: "51",
      queue_status: "failed",
      queue_attempts: 1,
      queue_max_attempts: 1,
      last_error: "render failed once",
      can_retry: true,
    };

    vi.mocked(api.retryWorkflowProduction).mockImplementation(async () => {
      mockState.project = {
        ...mockState.project,
        workflow_state: "production_queued",
        status: "production_queued",
      };
      mockState.summary = {
        ...mockState.summary,
        workflow_state: "production_queued",
      };
      mockState.productionStatus = {
        ...mockState.productionStatus,
        workflow_state: "production_queued",
        queue_status: "queued",
        queue_attempts: 0,
        last_error: null,
        can_retry: false,
      };
      return clone(mockState.productionStatus);
    });

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(
      await screen.findByRole("button", { name: /Retry Production/i }, { timeout: 30000 })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Retry Production/i }));

    await waitFor(() => {
      expect(api.retryWorkflowProduction).toHaveBeenCalledWith("project-1");
    }, { timeout: 8000 });

    await waitFor(() => {
      expect(screen.getByText(/Video production has been queued again/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    expect(screen.queryByRole("button", { name: /Retry Production/i })).toBeNull();
  }, 20000);

  it("shows production failure details clearly inside the create flow", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_failed",
      status: "production_failed",
      script_approved: "Approved script",
      character_package_approved: true,
      selected_character_ids: ["char-1"],
      production_job_id: "51",
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_failed",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_failed",
      production_job_id: "51",
      queue_status: "failed",
      queue_attempts: 1,
      queue_max_attempts: 1,
      last_error: "render failed once",
      can_retry: true,
    };

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    await waitFor(() => {
      expect(screen.getAllByText(/Production failed/i).length).toBeGreaterThan(0);
    });
  }, 20000);

  it("requires final approval confirmation before video production can start", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_ready",
      status: "production_ready",
      script_approved: "Approved script",
      script_approved_at: "2026-03-22T00:10:00",
      character_package_approved: true,
      character_package_approved_at: "2026-03-22T00:15:00",
      selected_character_ids: ["char-1"],
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_ready",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_ready",
    };

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    const finalApproval = await screen.findByRole("checkbox", {
      name: /I approve this script and cast for full video production/i,
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Start Video Production/i })).toBeDisabled();
    });

    await waitFor(() => {
      expect(finalApproval).toBeEnabled();
    });
    expect(screen.getByText(/This is the final approval step before rendering begins/i)).toBeInTheDocument();
  }, 20000);

  it("shows the production stage as ready after script and character approval", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_ready",
      status: "production_ready",
      script_approved: "Approved script",
      script_approved_at: "2026-03-22T00:10:00",
      character_package_approved: true,
      character_package_approved_at: "2026-03-22T00:15:00",
      selected_character_ids: ["char-1"],
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_ready",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_ready",
    };

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    const finalApproval = await screen.findByRole("checkbox", {
      name: /I approve this script and cast for full video production/i,
    });

    expect(finalApproval).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start Video Production/i })).toBeDisabled();
  });

  it("shows character slot usage alongside the credit summary", async () => {
    render(<HomePage />);

    expect(await screen.findByText(/Credits: 120 left/i)).toBeInTheDocument();
  });

  it("locks character creation when the saved library is full and offers a slot purchase", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "script_approved",
      script_approved: "Approved script",
      script_approved_at: "2026-03-22T00:00:00",
    };
    mockState.credits = {
      ...clone(mockState.defaults.credits),
      character_slots: {
        base_slots: 10,
        extra_slots: 0,
        total_slots: 10,
        used_slots: 10,
        remaining_slots: 0,
        addon_pack_size: 5,
        addon_pack_cost_credits: 50,
        is_full: true,
      },
    };

    render(<HomePage />);

    fireEvent.click(navButton(/^Manual-Create$/i));

    const addButton = await screen.findByRole("button", { name: /Add Character/i });
    const generateButton = screen.getByRole("button", { name: /Generate Character/i });
    const uploadButton = screen.getByRole("button", { name: /Upload Character/i });
    const buySlotsButton = screen.getByRole("button", { name: /Buy \+5 Slots/i });

    expect(addButton).toBeDisabled();
    expect(generateButton).toBeDisabled();
    expect(uploadButton).toBeDisabled();
    expect(screen.getByText(/saved character gallery is full/i)).toBeInTheDocument();

    fireEvent.click(buySlotsButton);

    await waitFor(() => {
      expect(api.purchaseCharacterSlotPack).toHaveBeenCalledWith({ pack_count: 1 });
    });
  }, 20000);

  it("shows project archive and duplicate controls in the simplified projects view", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Projects/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Projects/i));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Duplicate/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Archive/i })).toBeInTheDocument();
    expect(screen.getByText(/Step: Review Script/i)).toBeInTheDocument();
  }, 20000);

  it("shows simple reuse actions in the library for scripts and videos", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "video_completed",
      status: "video_completed",
      script_approved: "Approved story script",
      character_package_approved: true,
      final_video_url: "https://example.test/final-video.mp4",
    };
    mockState.library = {
      characters: [],
      scripts: [clone(mockState.project)],
      videos: [clone(mockState.project)],
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Library/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(navButton(/Library/i));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Scripts$/i }));
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Duplicate Into New Project/i })).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Videos$/i }));
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Open$/i })).toBeInTheDocument();
    }, { timeout: 15000 });

    expect(screen.getByRole("button", { name: /Reuse As New Project/i })).toBeInTheDocument();
    const deleteAllProjectsButton = screen.getByRole("button", { name: /Delete all projects/i });
    expect(deleteAllProjectsButton).toBeInTheDocument();
    fireEvent.click(deleteAllProjectsButton);
    await waitFor(() => {
      expect(vi.mocked(api.deleteWorkflowProjects)).toHaveBeenCalled();
    });
  }, 20000);

  it("hides blank character slots from the library and characters views", async () => {
    const blankCharacter = {
      character_id: "character-empty",
      name: "   ",
      role_type: "supporting",
      description: "   ",
      visual_prompt_base: "",
      negative_prompt_base: "",
      consistency_seed: "seed-empty",
      identity_hash: "hash-empty",
      lock_identity: true,
      reference_image_url: null,
      reference_image_urls: [],
      canonical_image_url: null,
      personality_traits: [],
      voice_profile: "default",
      created_at: "2026-04-03T00:00:00",
      updated_at: "2026-04-03T00:00:00",
    };
    const visibleCharacter = {
      ...blankCharacter,
      character_id: "character-visible",
      name: "Visible Character",
      description: "A real saved character.",
    };
    mockState.library = {
      characters: [blankCharacter, visibleCharacter],
      scripts: [],
      videos: [],
    };
    mockState.characters = {
      library: [blankCharacter, visibleCharacter],
      selected_character_ids: [],
      selected: [],
      approved_character_ids: [],
      approved_at: null,
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Library/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Library/i));

    await waitFor(() => {
      expect(screen.getByText("Visible Character")).toBeInTheDocument();
    });
    expect(screen.getAllByRole("article")).toHaveLength(1);
  }, 20000);

  it("lets users add a character from the collapsible auto-create builder", async () => {
    mockState.library = {
      characters: [],
      scripts: [],
      videos: [],
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Library/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Auto-Create/i));

    const builderToggle = await screen.findByRole("button", { name: /Character Builder/i });
    fireEvent.click(builderToggle);

    const builderScope = within(builderToggle.parentElement as HTMLElement);

    const nameField = await screen.findByPlaceholderText("My Main Character");
    fireEvent.change(nameField, { target: { value: "Auto Builder Lead" } });
    fireEvent.change(screen.getByLabelText(/^Role$/i), { target: { value: "main" } });
    fireEvent.change(screen.getByPlaceholderText(/A short description/i), {
      target: { value: "A character added from auto-create." },
    });
    fireEvent.click(builderScope.getByRole("button", { name: /^Add Character$/i }));

    await waitFor(() => {
      expect(vi.mocked(api.createLibraryCharacter)).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Auto Builder Lead",
          role_type: "main",
          description: "A character added from auto-create.",
        })
      );
    });

    fireEvent.click(navButton(/Library/i));
    await waitFor(() => {
      expect(screen.getByText("Auto Builder Lead")).toBeInTheDocument();
    });
  }, 20000);

  it("shows a consolidated downloads tab with the completed video download", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "video_completed",
      status: "video_completed",
      script_approved: "Approved story script",
      character_package_approved: true,
      final_video_url: "https://example.test/final-video.mp4",
    };
    mockState.library = {
      characters: [],
      scripts: [clone(mockState.project)],
      videos: [clone(mockState.project)],
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Download$/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(navButton(/^Download$/i));
    });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /^Download$/i })).toBeInTheDocument();
    }, { timeout: 15000 });
  });

  it("shows a full-screen play video tab for final validation", async () => {
    const requestFullscreen = vi.fn(async () => undefined);
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", {
      configurable: true,
      value: requestFullscreen,
    });

    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "video_completed",
      status: "video_completed",
      script_approved: "Approved story script",
      character_package_approved: true,
      final_video_url: "https://example.test/final-video.mp4",
    };
    mockState.library = {
      characters: [],
      scripts: [clone(mockState.project)],
      videos: [clone(mockState.project)],
    };

    const { container } = render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Playback/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Playback/i));

    await waitFor(() => {
      expect(requestFullscreen).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText(/Final video validation/i)).toBeInTheDocument();
    });
    expect(container.querySelector("video")).toBeInTheDocument();
  });

  it("lets a user connect a personal account and publish a finished video to it", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "video_completed",
      status: "video_completed",
      script_approved: "Approved story script",
      character_package_approved: true,
      final_video_url: "https://example.test/final-video.mp4",
    };
    mockState.library = {
      characters: [],
      scripts: [],
      videos: [clone(mockState.project)],
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Publish/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Publish/i));

    const singleTab = await screen.findByRole("tab", { name: /Single send/i }, { timeout: 15000 });
    const bulkTab = await screen.findByRole("tab", { name: /Bulk send/i }, { timeout: 15000 });
    expect(singleTab).toHaveAttribute("aria-selected", "true");
    fireEvent.click(bulkTab);
    expect(bulkTab).toHaveAttribute("aria-selected", "true");
    fireEvent.click(singleTab);

    const tiktokPlatform = await screen.findByRole("button", { name: /^TikTok$/i }, { timeout: 15000 });
    fireEvent.click(tiktokPlatform);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Account identifier/i)).toBeInTheDocument();
    }, { timeout: 15000 });
    fireEvent.change(screen.getByLabelText(/Account label/i), {
      target: { value: "My TikTok Channel" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Account identifier/i), {
      target: { value: "@mybrand" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save account/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Send now$/i })).toBeEnabled();
    }, { timeout: 15000 });

    fireEvent.change(screen.getByPlaceholderText(/Write the caption/i), {
      target: { value: "Launch day." },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Send now$/i }));

    await waitFor(() => {
      expect(vi.mocked(api.publishSocialVideos)).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: "project-1",
          message: "Launch day.",
          title: "Moonlight Rescue",
        })
      );
    });

    expect(await screen.findByText(/Published to tiktok:/i)).toBeInTheDocument();
  }, 20000);

  it("shows a minimal empty state when no projects exist yet", async () => {
    vi.mocked(api.fetchWorkflowProjects).mockImplementationOnce(async () => []);
    vi.mocked(api.fetchWorkflowLibrary).mockImplementationOnce(async () => ({
      characters: [],
      scripts: [],
      videos: [],
    }));

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/^Manual-Create$/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/^Manual-Create$/i));

    expect(screen.getByRole("button", { name: /^Generate Script$/i })).toBeInTheDocument();
    expect(screen.queryByText(/Start by entering a story request/i)).toBeNull();
  });

  it("opens a selected project back into the correct active create stage", async () => {
    mockState.project = {
      ...clone(mockState.defaults.project),
      workflow_state: "production_ready",
      status: "production_ready",
      script_approved: "Approved story script",
      script_approved_at: "2026-03-22T00:10:00",
      character_package_approved: true,
      character_package_approved_at: "2026-03-22T00:15:00",
      selected_character_ids: ["char-1"],
    };
    mockState.summary = {
      ...clone(mockState.defaults.summary),
      workflow_state: "production_ready",
      script_ready: true,
      characters_ready: true,
    };
    mockState.productionStatus = {
      ...clone(mockState.defaults.productionStatus),
      workflow_state: "production_ready",
    };

    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Projects/i)).toBeInTheDocument();
    });

    fireEvent.click(navButton(/Projects/i));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Continue Project/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Continue Project/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Step 4 Produce Video/i })).toBeEnabled();
    });

    expect(screen.getByText(/Ready when you are/i)).toBeInTheDocument();
  });
});
