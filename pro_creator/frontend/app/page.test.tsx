import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    },
  },
  project: {} as Record<string, unknown>,
  characters: {} as Record<string, unknown>,
  library: {} as Record<string, unknown>,
  summary: {} as Record<string, unknown>,
  productionStatus: {} as Record<string, unknown>,
  credits: {} as Record<string, unknown>,
}));

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
}

function navButton(label: RegExp): HTMLElement {
  return screen.getAllByRole("button", { name: label })[0];
}

vi.mock("../lib/api", () => ({
  fetchWorkflowProjects: vi.fn(async () => [clone(mockState.project)]),
  fetchWorkflowProject: vi.fn(async () => clone(mockState.project)),
  fetchWorkflowCharacters: vi.fn(async () => clone(mockState.characters)),
  fetchWorkflowLibrary: vi.fn(async () => clone(mockState.library)),
  fetchWorkflowProductionSummary: vi.fn(async () => clone(mockState.summary)),
  fetchWorkflowProductionStatus: vi.fn(async () => clone(mockState.productionStatus)),
  fetchMyCredits: vi.fn(async () => clone(mockState.credits)),
  createWorkflowProject: vi.fn(),
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
  approveWorkflowCharacters: vi.fn(),
  startWorkflowProduction: vi.fn(async () => ({
    project: clone(mockState.project),
    status: clone(mockState.productionStatus),
    video_path: null,
  })),
  retryWorkflowProduction: vi.fn(async () => clone(mockState.productionStatus)),
}));

describe("Workflow home page", () => {
  beforeEach(() => {
    resetMockState();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows only the simplified four-item navigation", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(navButton(/Overview/i)).toBeInTheDocument();
    });

    ["Overview", "Projects", "Create", "Library"].forEach((label) => {
      expect(navButton(new RegExp(label, "i"))).toBeInTheDocument();
    });

    ["Engines", "Automation", "Orchestration", "Logs"].forEach((label) => {
      expect(screen.queryByRole("button", { name: new RegExp(label, "i") })).toBeNull();
    });
  });

  it("keeps future workflow steps disabled until earlier approvals exist", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Review Script/i })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Step 2 Review Script/i })).toBeEnabled();
    });

    expect(screen.getByRole("button", { name: /Step 1 Story Request/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Step 3 Choose Characters/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Step 4 Produce Video/i })).toBeDisabled();
  });

  it("shows clear guided warnings before later workflow gates unlock", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText(/Review the draft and approve the script/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Approve the script to unlock character selection/i)).toBeInTheDocument();
    expect(screen.getByText(/Current step: Review Script/i)).toBeInTheDocument();
  });

  it("shows explicit per-step status banners inside the create flow", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText(/Draft ready/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Review required/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting on Step 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting on Step 3/i)).toBeInTheDocument();
  });

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
  });

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

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Retry Production/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Retry Production/i }));

    await waitFor(() => {
      expect(api.retryWorkflowProduction).toHaveBeenCalledWith("project-1");
    });

    await waitFor(() => {
      expect(screen.getByText(/Video production has been queued again/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: /Retry Production/i })).toBeNull();
  });

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

    const finalApproval = await screen.findByRole("checkbox", {
      name: /I approve this script and cast for full video production/i,
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Start Video Production/i })).toBeDisabled();
    });

    expect(finalApproval).toBeEnabled();
    expect(screen.getByText(/This is the final approval step before rendering begins/i)).toBeInTheDocument();
  });

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
    expect(screen.getByText(/Current step: Review Script/i)).toBeInTheDocument();
  });

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
      fireEvent.click(navButton(/Library Characters, scripts, and videos/i));
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
      expect(screen.getByRole("link", { name: /Download Video/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Reuse As New Project/i })).toBeInTheDocument();
  });

  it("shows a guided empty state when no projects exist yet", async () => {
    vi.mocked(api.fetchWorkflowProjects).mockImplementationOnce(async () => []);
    vi.mocked(api.fetchWorkflowLibrary).mockImplementationOnce(async () => ({
      characters: [],
      scripts: [],
      videos: [],
    }));

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText(/Start with a title or a short idea/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Start with a title or a short idea/i)).toBeInTheDocument();
    expect(screen.getByText(/Start by entering a story request/i)).toBeInTheDocument();
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
