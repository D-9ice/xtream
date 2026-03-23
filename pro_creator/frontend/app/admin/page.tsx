"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { BillingPricingSettings, CreditBalance } from "../../lib/api";
import {
  fetchAdmin2FAStatus,
  fetchAdminBillingPricing,
  fetchAdminSubscriptions,
  updateAdminBillingPricing,
  updateAdminSubscription,
  verifyAdminAccess,
} from "../../lib/api";

type BillingPricingForm = {
  moderate_credits: number;
  moderate_price_usd: number;
  moderate_base_character_slots: number;
  moderate_stripe_price_id: string;
  pro_credits: number;
  pro_price_usd: number;
  pro_base_character_slots: number;
  pro_stripe_price_id: string;
  studio_credits: number;
  studio_price_usd: number;
  studio_base_character_slots: number;
  studio_stripe_price_id: string;
  free_base_character_slots: number;
  character_slot_addon_size: number;
  character_slot_addon_cost_credits: number;
};

const DEFAULT_PRICING_FORM: BillingPricingForm = {
  moderate_credits: 500,
  moderate_price_usd: 15,
  moderate_base_character_slots: 5,
  moderate_stripe_price_id: "",
  pro_credits: 2000,
  pro_price_usd: 49,
  pro_base_character_slots: 10,
  pro_stripe_price_id: "",
  studio_credits: 6000,
  studio_price_usd: 119,
  studio_base_character_slots: 15,
  studio_stripe_price_id: "",
  free_base_character_slots: 5,
  character_slot_addon_size: 5,
  character_slot_addon_cost_credits: 50,
};

function pricingFormFromSettings(settings: BillingPricingSettings): BillingPricingForm {
  const moderate = settings.plans.find((plan) => plan.id === "moderate");
  const pro = settings.plans.find((plan) => plan.id === "pro");
  const studio = settings.plans.find((plan) => plan.id === "studio");
  return {
    moderate_credits: moderate?.credits ?? DEFAULT_PRICING_FORM.moderate_credits,
    moderate_price_usd: moderate?.price_usd ?? DEFAULT_PRICING_FORM.moderate_price_usd,
    moderate_base_character_slots:
      moderate?.base_character_slots ?? DEFAULT_PRICING_FORM.moderate_base_character_slots,
    moderate_stripe_price_id: moderate?.stripe_price_id ?? "",
    pro_credits: pro?.credits ?? DEFAULT_PRICING_FORM.pro_credits,
    pro_price_usd: pro?.price_usd ?? DEFAULT_PRICING_FORM.pro_price_usd,
    pro_base_character_slots: pro?.base_character_slots ?? DEFAULT_PRICING_FORM.pro_base_character_slots,
    pro_stripe_price_id: pro?.stripe_price_id ?? "",
    studio_credits: studio?.credits ?? DEFAULT_PRICING_FORM.studio_credits,
    studio_price_usd: studio?.price_usd ?? DEFAULT_PRICING_FORM.studio_price_usd,
    studio_base_character_slots:
      studio?.base_character_slots ?? DEFAULT_PRICING_FORM.studio_base_character_slots,
    studio_stripe_price_id: studio?.stripe_price_id ?? "",
    free_base_character_slots: settings.free_base_character_slots,
    character_slot_addon_size: settings.character_slot_addon_size,
    character_slot_addon_cost_credits: settings.character_slot_addon_cost_credits,
  };
}

export default function AdminPage() {
  const [hasMounted, setHasMounted] = useState(false);
  const [gateLoading, setGateLoading] = useState(true);
  const [gateError, setGateError] = useState<string | null>(null);
  const [dashboardPassword, setDashboardPassword] = useState("");
  const [showDashboardPassword, setShowDashboardPassword] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [twoFaDetail, setTwoFaDetail] = useState<string | null>(null);
  const [twoFaEnabled, setTwoFaEnabled] = useState(false);
  const [hasAdminAccess, setHasAdminAccess] = useState(false);

  const [items, setItems] = useState<CreditBalance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEmail, setSelectedEmail] = useState("");
  const [planName, setPlanName] = useState("free");
  const [status, setStatus] = useState("active");
  const [creditsDelta, setCreditsDelta] = useState(0);
  const [pricingForm, setPricingForm] = useState<BillingPricingForm>(DEFAULT_PRICING_FORM);
  const [pricingLoading, setPricingLoading] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  useEffect(() => {
    if (!hasMounted) {
      return;
    }
    let active = true;
    setGateLoading(true);
    setGateError(null);
    fetchAdmin2FAStatus()
      .then((statusResponse) => {
        if (!active) {
          return;
        }
        setTwoFaEnabled(Boolean(statusResponse.enabled));
        setTwoFaDetail(statusResponse.detail ?? null);
      })
      .catch((err) => {
        if (active) {
          setGateError(err instanceof Error ? err.message : "Failed to load admin access");
        }
      })
      .finally(() => {
        if (active) {
          setGateLoading(false);
        }
      });

    const token = window.sessionStorage.getItem("pc_admin_access_token");
    setHasAdminAccess(Boolean(token));

    return () => {
      active = false;
    };
  }, [hasMounted]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [subscriptionResponse, pricingResponse] = await Promise.all([
        fetchAdminSubscriptions(),
        fetchAdminBillingPricing(),
      ]);
      setItems(subscriptionResponse.items);
      setPricingForm(pricingFormFromSettings(pricingResponse));
      if (!selectedEmail && subscriptionResponse.items.length > 0) {
        setSelectedEmail(subscriptionResponse.items[0].email);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, [selectedEmail]);

  useEffect(() => {
    if (hasAdminAccess) {
      load();
    }
  }, [hasAdminAccess, load]);

  const handleUnlock = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setGateError(null);
    if (!dashboardPassword) {
      setGateError("Enter the admin dashboard password.");
      return;
    }
    setGateLoading(true);
    try {
      const verify = await verifyAdminAccess({
        password: dashboardPassword,
        otp_code: otpCode || undefined,
      });
      window.sessionStorage.setItem("pc_admin_access_token", verify.access_token);
      setHasAdminAccess(true);
      setDashboardPassword("");
      setOtpCode("");
      await load();
    } catch (err) {
      setGateError(err instanceof Error ? err.message : "Failed to unlock admin dashboard");
    } finally {
      setGateLoading(false);
    }
  };

  const handleLock = () => {
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.removeItem("pc_admin_access_token");
    setHasAdminAccess(false);
    setItems([]);
  };

  const handleUpdate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedEmail) {
      setError("Select a user");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await updateAdminSubscription(selectedEmail, {
        plan_name: planName,
        status,
        credits_delta: creditsDelta,
      });
      await load();
      setCreditsDelta(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update subscription");
    } finally {
      setLoading(false);
    }
  };

  const handlePricingUpdate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPricingLoading(true);
    setError(null);
    try {
      const response = await updateAdminBillingPricing({
        ...pricingForm,
        moderate_stripe_price_id: pricingForm.moderate_stripe_price_id || undefined,
        pro_stripe_price_id: pricingForm.pro_stripe_price_id || undefined,
        studio_stripe_price_id: pricingForm.studio_stripe_price_id || undefined,
      });
      setPricingForm(pricingFormFromSettings(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update pricing");
    } finally {
      setPricingLoading(false);
    }
  };

  const subtitle = useMemo(() => {
    if (gateLoading) {
      return "Loading admin access controls...";
    }
    if (gateError) {
      return gateError;
    }
    if (twoFaEnabled) {
      return twoFaDetail ?? "2FA is enabled.";
    }
    return twoFaDetail ?? "2FA is deactivated.";
  }, [gateError, gateLoading, twoFaDetail, twoFaEnabled]);

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-3xl font-bold text-white">Admin Dashboard</h1>
            <p className="text-xs uppercase tracking-[0.25em] text-slate-400">
              Subscription Management
            </p>
          </div>
          <a
            className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200"
            href="/"
          >
            Back to app
          </a>
        </div>
      </header>
      {!hasMounted ? (
        <main className="mx-auto max-w-6xl px-6 py-6">
          <p className="text-xs text-slate-400">Loading...</p>
        </main>
      ) : !hasAdminAccess ? (
        <main className="mx-auto max-w-3xl px-6 py-10">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-6">
            <h2 className="text-2xl font-bold text-white">Admin Access</h2>
            <p className="mt-2 text-sm text-slate-300">{subtitle}</p>
            <form className="mt-6 space-y-3" onSubmit={handleUnlock}>
              <div>
                <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="dashboard-password">
                  Dashboard password
                </label>
                <div className="relative mt-2">
                  <input
                    id="dashboard-password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 pr-11 text-sm text-white"
                    type={showDashboardPassword ? "text" : "password"}
                    value={dashboardPassword}
                    onChange={(event) => setDashboardPassword(event.target.value)}
                    placeholder="Enter the admin dashboard password."
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 right-3 flex items-center text-slate-400 transition hover:text-slate-200"
                    aria-label={showDashboardPassword ? "Hide dashboard password" : "Show dashboard password"}
                    onClick={() => setShowDashboardPassword((value) => !value)}
                  >
                    {showDashboardPassword ? (
                      <svg
                        aria-hidden="true"
                        viewBox="0 0 24 24"
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10.584 10.584a2 2 0 002.832 2.832" />
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M7.5 7.5C5.018 9.086 3.56 11.2 3 12c1.35 1.95 4.838 6 9 6 1.545 0 2.96-.474 4.125-1.178"
                        />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14.12 14.12A3 3 0 009.88 9.88" />
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
                        className="h-5 w-5"
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
                <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="otp-code">
                  OTP code
                </label>
                <input
                  id="otp-code"
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                  type="text"
                  value={otpCode}
                  onChange={(event) => setOtpCode(event.target.value)}
                  placeholder={twoFaEnabled ? "Enter OTP code." : "2FA is deactivated"}
                  disabled={!twoFaEnabled}
                />
              </div>
              {gateError ? (
                <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                  {gateError}
                </p>
              ) : null}
              <button
                className="w-full rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-sm font-semibold text-aurora"
                type="submit"
                disabled={gateLoading}
              >
                {gateLoading ? "Checking..." : "Unlock admin dashboard"}
              </button>
            </form>
          </section>
        </main>
      ) : (
        <main className="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:grid-cols-[1.4fr_0.9fr]">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Users and Credits</h2>
                <p className="text-xs text-slate-400">{subtitle}</p>
              </div>
              <button
                type="button"
                className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-200"
                onClick={handleLock}
              >
                Lock
              </button>
            </div>
            {error ? (
              <p className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                {error}
              </p>
            ) : null}
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400">
                    <th className="px-2 py-2">Email</th>
                    <th className="px-2 py-2">Plan</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Balance</th>
                    <th className="px-2 py-2">Used</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr
                      key={item.email}
                      className={`border-t border-slate-800 ${
                        selectedEmail === item.email ? "bg-slate-900/50" : ""
                      }`}
                      onClick={() => {
                        setSelectedEmail(item.email);
                        setPlanName(item.plan_name);
                        setStatus(item.status);
                      }}
                    >
                      <td className="px-2 py-2">{item.email}</td>
                      <td className="px-2 py-2">{item.plan_name}</td>
                      <td className="px-2 py-2">{item.status}</td>
                      <td className="px-2 py-2">{item.credits_balance}</td>
                      <td className="px-2 py-2">{item.credits_used_total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <h2 className="text-lg font-semibold text-white">Internal Tools</h2>
              <p className="mt-2 text-sm text-slate-400">
                Legacy engine-oriented screens are kept off the main user path and only exposed here for internal admin work.
              </p>
              <a
                className="mt-4 inline-flex rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora"
                href="/admin/internal"
              >
                Open Internal Dashboard
              </a>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <h2 className="text-lg font-semibold text-white">Update Subscription</h2>
              <form className="mt-4 space-y-3" onSubmit={handleUpdate}>
                <div>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    User
                  </label>
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                    value={selectedEmail}
                    onChange={(event) => setSelectedEmail(event.target.value)}
                  >
                    {items.map((item) => (
                      <option key={item.email} value={item.email}>
                        {item.email}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Plan
                  </label>
                  <input
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                    value={planName}
                    onChange={(event) => setPlanName(event.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Status
                  </label>
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                    value={status}
                    onChange={(event) => setStatus(event.target.value)}
                  >
                    <option value="active">active</option>
                    <option value="paused">paused</option>
                    <option value="canceled">canceled</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Credit Delta
                  </label>
                  <input
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                    type="number"
                    value={creditsDelta}
                    onChange={(event) => setCreditsDelta(Number(event.target.value))}
                  />
                </div>
                <button
                  className="w-full rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-sm font-semibold text-aurora"
                  type="submit"
                  disabled={loading}
                >
                  {loading ? "Saving..." : "Save changes"}
                </button>
              </form>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <h2 className="text-lg font-semibold text-white">Billing and Character Pricing</h2>
              <p className="mt-2 text-sm text-slate-400">
                Edit subscription credits, displayed prices, included character slots, and the credit cost of extra slot packs.
              </p>
              <form className="mt-4 space-y-5" onSubmit={handlePricingUpdate}>
                {[
                  ["moderate", "Moderate"],
                  ["pro", "Pro"],
                  ["studio", "Studio"],
                ].map(([planId, label]) => (
                  <div key={planId} className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                    <p className="text-sm font-semibold text-white">{label}</p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Credits
                        <input
                          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                          type="number"
                          value={pricingForm[`${planId}_credits` as keyof BillingPricingForm] as number}
                          onChange={(event) =>
                            setPricingForm((current) => ({
                              ...current,
                              [`${planId}_credits`]: Number(event.target.value),
                            }))
                          }
                        />
                      </label>
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Price USD
                        <input
                          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                          type="number"
                          value={pricingForm[`${planId}_price_usd` as keyof BillingPricingForm] as number}
                          onChange={(event) =>
                            setPricingForm((current) => ({
                              ...current,
                              [`${planId}_price_usd`]: Number(event.target.value),
                            }))
                          }
                        />
                      </label>
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Base Character Slots
                        <input
                          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                          type="number"
                          value={
                            pricingForm[
                              `${planId}_base_character_slots` as keyof BillingPricingForm
                            ] as number
                          }
                          onChange={(event) =>
                            setPricingForm((current) => ({
                              ...current,
                              [`${planId}_base_character_slots`]: Number(event.target.value),
                            }))
                          }
                        />
                      </label>
                      <label className="text-xs uppercase tracking-wide text-slate-400">
                        Stripe Price ID
                        <input
                          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                          value={pricingForm[`${planId}_stripe_price_id` as keyof BillingPricingForm] as string}
                          onChange={(event) =>
                            setPricingForm((current) => ({
                              ...current,
                              [`${planId}_stripe_price_id`]: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </div>
                  </div>
                ))}

                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Free Base Slots
                    <input
                      className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                      type="number"
                      value={pricingForm.free_base_character_slots}
                      onChange={(event) =>
                        setPricingForm((current) => ({
                          ...current,
                          free_base_character_slots: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Add-on Pack Size
                    <input
                      className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                      type="number"
                      value={pricingForm.character_slot_addon_size}
                      onChange={(event) =>
                        setPricingForm((current) => ({
                          ...current,
                          character_slot_addon_size: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                  <label className="text-xs uppercase tracking-wide text-slate-400">
                    Add-on Cost Credits
                    <input
                      className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                      type="number"
                      value={pricingForm.character_slot_addon_cost_credits}
                      onChange={(event) =>
                        setPricingForm((current) => ({
                          ...current,
                          character_slot_addon_cost_credits: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                </div>

                <button
                  className="w-full rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-sm font-semibold text-aurora"
                  type="submit"
                  disabled={pricingLoading}
                >
                  {pricingLoading ? "Saving pricing..." : "Save pricing controls"}
                </button>
              </form>
            </div>
          </section>
        </main>
      )}
    </div>
  );
}
