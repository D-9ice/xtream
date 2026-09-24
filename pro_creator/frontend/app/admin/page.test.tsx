import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../lib/api";
import AdminPage from "./page";

const adminState = vi.hoisted(() => ({
  defaultSubscription: {
    email: "owner@example.com",
    plan_name: "pro",
    status: "active",
    credits_balance: 2400,
    credits_reserved: 0,
    credits_used_total: 120,
    renewal_date: null,
    extra_character_slots: 5,
    factory_mode_status: "inactive",
    factory_mode_access: "none",
    factory_mode_renewal_date: null,
    factory_mode_purchased_at: null,
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
  subscriptions: {
    items: [],
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
      {
        id: "factory_one_time",
        name: "Factory Mode One-Time",
        kind: "factory_access",
        credits: 0,
        price_usd: 149,
        base_character_slots: 0,
        stripe_price_id: "price_factory_one_time",
        checkout_enabled: true,
        access_mode: "one_time",
      },
      {
        id: "factory_subscription",
        name: "Factory Mode Subscription",
        kind: "factory_access",
        credits: 0,
        price_usd: 39,
        base_character_slots: 0,
        stripe_price_id: "price_factory_subscription",
        checkout_enabled: true,
        access_mode: "subscription",
        access_days: 30,
      },
    ],
    receipts_live_mode: false,
    owner_mode_enabled: false,
    free_base_character_slots: 100,
    character_slot_addon_size: 5,
    character_slot_addon_cost_credits: 50,
  },
  analytics: {
    total_visits: 24,
    human_visits: 18,
    bot_visits: 6,
    unique_sessions: 12,
    unique_paths: 7,
    visits_last_24h: 5,
    visits_last_7d: 14,
    top_paths: [
      {
        path: "/",
        visits: 9,
        human_visits: 8,
        bot_visits: 1,
      },
    ],
    top_devices: [
      {
        label: "desktop",
        visits: 16,
        human_visits: 14,
        bot_visits: 2,
      },
      {
        label: "mobile",
        visits: 8,
        human_visits: 4,
        bot_visits: 4,
      },
    ],
    top_countries: [
      {
        label: "GH",
        visits: 12,
        human_visits: 10,
        bot_visits: 2,
      },
      {
        label: "US",
        visits: 12,
        human_visits: 8,
        bot_visits: 4,
      },
    ],
    recent_visits: [
      {
        visit_id: "visit-1",
        path: "/",
        referrer: null,
        device_type: "desktop",
        country_code: "GH",
        page_title: "Pro Creator Pro",
        session_id: "session-1",
        event_type: "page_view",
        is_bot: false,
        bot_reason: null,
        created_at: "2026-04-09T10:00:00.000Z",
      },
    ],
    daily_visits: [
      {
        day: "2026-04-09",
        visits: 5,
        human_visits: 4,
        bot_visits: 1,
      },
    ],
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
  updateAdminSubscription: vi.fn(async (_email, payload) => {
    adminState.subscriptions.items[0] = {
      ...adminState.subscriptions.items[0],
      plan_name: payload.plan_name ?? adminState.subscriptions.items[0].plan_name,
      status: payload.status ?? adminState.subscriptions.items[0].status,
      factory_mode_access:
        (payload.factory_mode_access as string | undefined) ?? adminState.subscriptions.items[0].factory_mode_access,
      factory_mode_status:
        payload.factory_mode_access === "none"
          ? "inactive"
          : payload.factory_mode_access
            ? "active"
            : adminState.subscriptions.items[0].factory_mode_status,
      factory_mode_renewal_date:
        payload.factory_mode_renewal_date ?? adminState.subscriptions.items[0].factory_mode_renewal_date,
    };
    return adminState.subscriptions.items[0];
  }),
  fetchAdminBillingPricing: vi.fn(async () => adminState.pricing),
  fetchAdminVisitAnalyticsSummary: vi.fn(async () => adminState.analytics),
  fetchAdminSocialConnections: vi.fn(async () => ({ items: [] })),
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
      if (plan.id === "factory_one_time") {
        return {
          ...plan,
          price_usd: payload.factory_one_time_price_usd,
          stripe_price_id: payload.factory_one_time_stripe_price_id ?? null,
        };
      }
      if (plan.id === "factory_subscription") {
        return {
          ...plan,
          price_usd: payload.factory_subscription_price_usd,
          stripe_price_id: payload.factory_subscription_stripe_price_id ?? null,
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
    owner_mode_enabled: payload.owner_mode_enabled,
    receipts_live_mode: payload.receipts_live_mode,
  })),
  deleteAdminUser: vi.fn(async (email) => ({ deleted: true, email })),
  clearAdminTestPurchases: vi.fn(async () => ({
    deleted_count: 3,
    deleted_emails: [
      "test-a215a333a3@example.com",
      "test-723d097ea8@example.com",
      "test-abc4029366@example.com",
    ],
  })),
  saveAdminSocialConnection: vi.fn(async (payload) => ({
    connection_id: payload.connection_id ?? "social-connection-1",
    platform: payload.platform,
    account_label: payload.account_label,
    account_identifier: payload.account_identifier ?? null,
    scopes: payload.scopes ?? [],
    metadata: payload.metadata ?? {},
    enabled: payload.enabled ?? true,
    token_expires_at: payload.token_expires_at ?? null,
    created_at: "2026-04-03T00:00:00",
    updated_at: "2026-04-03T00:00:00",
  })),
  deleteAdminSocialConnection: vi.fn(async () => ({ deleted: true })),
  clearBillingTransactionRecords: vi.fn(async () => ({
    deleted_count: 4,
  })),
}));

describe("Admin pricing dashboard", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.clearAllMocks();
    adminState.subscriptions.items = [
      {
        ...adminState.defaultSubscription,
        character_slots: {
          ...adminState.defaultSubscription.character_slots,
        },
      },
    ];
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
    const socialHeading = await screen.findByRole("heading", {
      name: /Social Publishing Credentials/i,
    });
    const analyticsHeading = await screen.findByRole("heading", {
      name: /Visitor Analytics/i,
    });

    expect(pricingHeading).toBeInTheDocument();
    expect(socialHeading).toBeInTheDocument();
    expect(analyticsHeading).toBeInTheDocument();
    expect(screen.getByText(/Top devices/i)).toBeInTheDocument();
    expect(screen.getByText(/Top countries/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(api.verifyAdminAccess).toHaveBeenCalledWith({
        password: "ChangeMe123!",
        otp_code: undefined,
      });
    });

    expect(api.fetchAdminSubscriptions).toHaveBeenCalled();
    expect(api.fetchAdminBillingPricing).toHaveBeenCalled();
    expect(api.fetchAdminVisitAnalyticsSummary).toHaveBeenCalled();
    expect(api.fetchAdminSocialConnections).toHaveBeenCalled();
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
    fireEvent.change(screen.getByDisplayValue("149"), {
      target: { value: "159" },
    });
    fireEvent.change(screen.getByDisplayValue("price_factory_one_time"), {
      target: { value: "price_factory_one_time_new" },
    });
    fireEvent.change(screen.getByDisplayValue("39"), {
      target: { value: "45" },
    });
    fireEvent.change(screen.getByDisplayValue("price_factory_subscription"), {
      target: { value: "price_factory_subscription_new" },
    });
    fireEvent.change(screen.getByLabelText(/Free Base Slots/i), {
      target: { value: "120" },
    });
    fireEvent.change(screen.getByLabelText(/Add-on Cost Credits/i), {
      target: { value: "80" },
    });
    fireEvent.click(screen.getByRole("switch", { name: /Receipt mode/i }));
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
          factory_one_time_price_usd: 159,
          factory_one_time_stripe_price_id: "price_factory_one_time_new",
          factory_subscription_price_usd: 45,
          factory_subscription_stripe_price_id: "price_factory_subscription_new",
          receipts_live_mode: true,
          free_base_character_slots: 120,
          character_slot_addon_cost_credits: 80,
        })
      );
    });
  }, 20000);

  it("toggles owner mode in the billing pricing editor", async () => {
    window.sessionStorage.setItem("pc_admin_access_token", "cached-admin-token");

    render(<AdminPage />);

    await screen.findByRole("heading", { name: /Billing and Character Pricing/i });

    fireEvent.click(screen.getByRole("switch", { name: /Owner mode/i }));

    await waitFor(() => {
      expect(api.updateAdminBillingPricing).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_mode_enabled: true,
        })
      );
    });
  }, 20000);

  it("updates factory mode access for a user from the admin editor", async () => {
    window.sessionStorage.setItem("pc_admin_access_token", "cached-admin-token");
    adminState.subscriptions.items[0] = {
      ...adminState.subscriptions.items[0],
      factory_mode_status: "active",
      factory_mode_access: "subscription",
      factory_mode_renewal_date: "2026-05-01T10:30:00.000Z",
    };

    render(<AdminPage />);

    await screen.findByRole("heading", { name: /Billing and Character Pricing/i });

    fireEvent.click(screen.getByRole("button", { name: /Factory Mode Subscription/i }));
    const renewalInput = await screen.findByLabelText(/Renewal date/i);
    fireEvent.change(renewalInput, {
      target: { value: "2026-05-01T10:30" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save changes/i }));
    const expectedRenewal = new Date("2026-05-01T10:30").toISOString();

    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({
          factory_mode_access: "subscription",
          factory_mode_renewal_date: expectedRenewal,
        })
      );
    });
  }, 20000);

  it("updates factory mode access for a user from the admin editor", async () => {
    window.sessionStorage.setItem("pc_admin_access_token", "cached-admin-token");
    adminState.subscriptions.items[0] = {
      ...adminState.subscriptions.items[0],
      factory_mode_status: "active",
      factory_mode_access: "subscription",
      factory_mode_renewal_date: "2026-05-01T10:30:00.000Z",
    };

    render(<AdminPage />);

    await screen.findByRole("heading", { name: /Billing and Character Pricing/i });

    fireEvent.click(screen.getByRole("button", { name: /Factory Mode Subscription/i }));
    const renewalInput = await screen.findByLabelText(/Renewal date/i);
    fireEvent.change(renewalInput, {
      target: { value: "2026-05-01T10:30" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Save changes/i }));

    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({
          factory_mode_access: "subscription",
          factory_mode_renewal_date: "2026-05-01T10:30:00.000Z",
        })
      );
    });
  }, 20000);

  it("suspends, bans, deletes, and clears test purchases from the admin dashboard", async () => {
    window.sessionStorage.setItem("pc_admin_access_token", "cached-admin-token");
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AdminPage />);

    await waitFor(() => {
      expect(api.fetchAdminSubscriptions).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: /^Suspend$/i }));
    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({ status: "suspended" })
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Unsuspend$/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^Unsuspend$/i }));
    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({ status: "active" })
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /^Ban$/i }));
    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({ status: "banned" })
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Unban$/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^Unban$/i }));
    await waitFor(() => {
      expect(api.updateAdminSubscription).toHaveBeenCalledWith(
        "owner@example.com",
        expect.objectContaining({ status: "active" })
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));
    await waitFor(() => {
      expect(api.deleteAdminUser).toHaveBeenCalledWith("owner@example.com");
    });

    fireEvent.click(screen.getByRole("button", { name: /Clear test purchases/i }));
    await waitFor(() => {
      expect(api.clearAdminTestPurchases).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Clear test records/i }));
    await waitFor(() => {
      expect(api.clearBillingTransactionRecords).toHaveBeenCalled();
    });

    confirmSpy.mockRestore();
  }, 20000);
});
