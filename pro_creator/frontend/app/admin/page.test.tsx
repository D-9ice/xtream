import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../lib/api";
import AdminPage from "./page";

const adminState = vi.hoisted(() => ({
  subscriptions: {
    items: [
      {
        email: "owner@example.com",
        plan_name: "pro",
        status: "active",
        credits_balance: 2400,
        credits_reserved: 0,
        credits_used_total: 120,
        renewal_date: null,
        extra_character_slots: 5,
        character_slots: {
          base_slots: 10,
          extra_slots: 5,
          total_slots: 15,
          used_slots: 7,
          remaining_slots: 8,
          addon_pack_size: 5,
          addon_pack_cost_credits: 50,
          is_full: false,
        },
      },
    ],
  },
  pricing: {
    plans: [
      {
        id: "moderate",
        name: "Moderate",
        credits: 500,
        price_usd: 15,
        base_character_slots: 5,
        stripe_price_id: "price_moderate",
        checkout_enabled: true,
      },
      {
        id: "pro",
        name: "Pro",
        credits: 2000,
        price_usd: 49,
        base_character_slots: 10,
        stripe_price_id: "price_pro",
        checkout_enabled: true,
      },
      {
        id: "studio",
        name: "Studio",
        credits: 6000,
        price_usd: 119,
        base_character_slots: 15,
        stripe_price_id: "price_studio",
        checkout_enabled: true,
      },
    ],
    free_base_character_slots: 100,
    character_slot_addon_size: 5,
    character_slot_addon_cost_credits: 50,
  },
}));

vi.mock("../../lib/api", () => ({
  fetchAdmin2FAStatus: vi.fn(async () => ({
    enabled: false,
    method: "totp",
    detail: "2FA is currently disabled. Password-only admin access is active.",
  })),
  verifyAdminAccess: vi.fn(async () => ({
    access_token: "admin-token",
    expires_in_seconds: 900,
  })),
  fetchAdminSubscriptions: vi.fn(async () => adminState.subscriptions),
  updateAdminSubscription: vi.fn(async () => adminState.subscriptions.items[0]),
  fetchAdminBillingPricing: vi.fn(async () => adminState.pricing),
  updateAdminBillingPricing: vi.fn(async (payload) => ({
    ...adminState.pricing,
    plans: adminState.pricing.plans.map((plan) => {
      if (plan.id === "moderate") {
        return {
          ...plan,
          credits: payload.moderate_credits,
          price_usd: payload.moderate_price_usd,
          base_character_slots: payload.moderate_base_character_slots,
          stripe_price_id: payload.moderate_stripe_price_id ?? null,
        };
      }
      if (plan.id === "pro") {
        return {
          ...plan,
          credits: payload.pro_credits,
          price_usd: payload.pro_price_usd,
          base_character_slots: payload.pro_base_character_slots,
          stripe_price_id: payload.pro_stripe_price_id ?? null,
        };
      }
      return {
        ...plan,
        credits: payload.studio_credits,
        price_usd: payload.studio_price_usd,
        base_character_slots: payload.studio_base_character_slots,
        stripe_price_id: payload.studio_stripe_price_id ?? null,
      };
    }),
    free_base_character_slots: payload.free_base_character_slots,
    character_slot_addon_size: payload.character_slot_addon_size,
    character_slot_addon_cost_credits: payload.character_slot_addon_cost_credits,
  })),
}));

describe("Admin pricing dashboard", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.clearAllMocks();
  });

  it("unlocks the admin dashboard and loads the pricing editor", async () => {
    render(<AdminPage />);

    expect(await screen.findByRole("heading", { name: /Admin Access/i })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Enter the admin dashboard password\./i), {
      target: { value: "ChangeMe123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Unlock admin dashboard/i }));

    const pricingHeading = await screen.findByRole("heading", {
      name: /Billing and Character Pricing/i,
    });

    expect(pricingHeading).toBeInTheDocument();

    await waitFor(() => {
      expect(api.verifyAdminAccess).toHaveBeenCalledWith({
        password: "ChangeMe123!",
        otp_code: undefined,
      });
    });

    expect(api.fetchAdminSubscriptions).toHaveBeenCalled();
    expect(api.fetchAdminBillingPricing).toHaveBeenCalled();
    expect(screen.getByDisplayValue("2000")).toBeInTheDocument();
    expect(screen.getByDisplayValue("50")).toBeInTheDocument();
  }, 20000);

  it("submits pricing changes from the admin editor", async () => {
    window.sessionStorage.setItem("pc_admin_access_token", "cached-admin-token");

    render(<AdminPage />);

    const pricingHeading = await screen.findByRole("heading", {
      name: /Billing and Character Pricing/i,
    });
    const pricingSection = pricingHeading.closest("div");

    expect(pricingSection).not.toBeNull();

    await waitFor(() => {
      expect(api.fetchAdminSubscriptions).toHaveBeenCalled();
      expect(api.fetchAdminBillingPricing).toHaveBeenCalled();
    });

    const proCard = within(pricingSection as HTMLElement).getByText(/^Pro$/).closest("div");
    const moderateCard = within(pricingSection as HTMLElement).getByText(/^Moderate$/).closest("div");

    expect(proCard).not.toBeNull();
    expect(moderateCard).not.toBeNull();

    fireEvent.change(within(proCard as HTMLElement).getByDisplayValue("2000"), {
      target: { value: "2500" },
    });
    fireEvent.change(within(proCard as HTMLElement).getByDisplayValue("49"), {
      target: { value: "59" },
    });
    fireEvent.change(within(proCard as HTMLElement).getByDisplayValue("10"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText(/Free Base Slots/i), {
      target: { value: "120" },
    });
    fireEvent.change(screen.getByLabelText(/Add-on Cost Credits/i), {
      target: { value: "80" },
    });
    fireEvent.change(within(moderateCard as HTMLElement).getByDisplayValue("price_moderate"), {
      target: { value: "price_moderate_new" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save pricing controls/i }));

    await waitFor(() => {
      expect(api.updateAdminBillingPricing).toHaveBeenCalledWith(
        expect.objectContaining({
          moderate_stripe_price_id: "price_moderate_new",
          pro_credits: 2500,
          pro_price_usd: 59,
          pro_base_character_slots: 12,
          free_base_character_slots: 120,
          character_slot_addon_cost_credits: 80,
        })
      );
    });
  }, 20000);
});
