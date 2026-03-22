import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HomePage from "./page";

const workflowProject = {
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
} as const;

vi.mock("../lib/api", () => ({
  fetchWorkflowProjects: vi.fn(async () => [workflowProject]),
  fetchWorkflowProject: vi.fn(async () => workflowProject),
  fetchWorkflowCharacters: vi.fn(async () => ({
    library: [],
    selected_character_ids: [],
    selected: [],
    approved_character_ids: [],
    approved_at: null,
  })),
  fetchWorkflowLibrary: vi.fn(async () => ({
    characters: [],
    scripts: [],
    videos: [],
  })),
  fetchWorkflowProductionSummary: vi.fn(async () => ({
    project_id: workflowProject.project_id,
    workflow_state: workflowProject.workflow_state,
    script_ready: false,
    characters_ready: false,
    estimated_credits: 20,
    current_credit_balance: 120,
    target_duration_minutes: 4,
    selected_characters: [],
    final_video_url: null,
  })),
  fetchMyCredits: vi.fn(async () => ({
    email: "owner@example.com",
    plan_name: "pro",
    status: "active",
    credits_balance: 120,
    credits_reserved: 0,
    credits_used_total: 0,
    renewal_date: null,
  })),
  createWorkflowProject: vi.fn(),
  updateWorkflowProject: vi.fn(),
  generateWorkflowScript: vi.fn(),
  approveWorkflowScript: vi.fn(),
  regenerateWorkflowScript: vi.fn(),
  updateWorkflowScript: vi.fn(),
  selectWorkflowCharacters: vi.fn(),
  createWorkflowCharacter: vi.fn(),
  generateWorkflowCharacter: vi.fn(),
  uploadWorkflowCharacter: vi.fn(),
  approveWorkflowCharacters: vi.fn(),
  startWorkflowProduction: vi.fn(),
}));

describe("Workflow home page", () => {
  it("shows only the simplified four-item navigation", async () => {
    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Overview/i })).toBeInTheDocument();
    });

    ["Overview", "Projects", "Create", "Library"].forEach((label) => {
      expect(screen.getByRole("button", { name: new RegExp(label, "i") })).toBeInTheDocument();
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

    expect(screen.getByRole("button", { name: /^Story Request$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Review Script$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Choose Characters$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Produce Video$/i })).toBeDisabled();
  });
});
