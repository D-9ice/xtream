import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FactoryModePage from "./page";

const mockNavigation = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockNavigation.push,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("../../lib/api", () => ({
  fetchMyCredits: vi.fn(async () => ({
    email: "owner@example.com",
    plan_name: "pro",
    status: "active",
    credits_balance: 120,
    credits_used_total: 0,
    owner_mode_enabled: false,
    factory_mode_status: "inactive",
    factory_mode_access: "none",
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
  })),
  fetchOrchestrationRunnerStatus: vi.fn(async () => ({
    enabled: true,
    running: false,
    interval_seconds: 5,
    detail: null,
  })),
  enqueueOrchestrationJob: vi.fn(),
  startOrchestrationRunner: vi.fn(),
  stopOrchestrationRunner: vi.fn(),
}));

describe("Factory mode page", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.clearAllMocks();
    mockNavigation.push.mockReset();
  });

  it("renders the dedicated Factory Mode page shell", async () => {
    render(<FactoryModePage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Factory Mode/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: /Back to app/i })).toBeInTheDocument();
  });

  it("opens credits and plans from the factory access prompt", async () => {
    render(<FactoryModePage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Open Credits & Plans/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Open Credits & Plans/i }));

    expect(mockNavigation.push).toHaveBeenCalledWith("/?credits=1");
  });
});
