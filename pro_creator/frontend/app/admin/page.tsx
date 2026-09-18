"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  BillingPricingSettings,
  CreditBalance,
  SocialAccountConnection,
  VisitAnalyticsSummary,
} from "../../lib/api";
import {
  clearAdminTestPurchases,
  clearBillingTransactionRecords,
  deleteAdminUser,
  fetchAdmin2FAStatus,
  fetchAdminBillingPricing,
  fetchAdminVisitAnalyticsSummary,
  fetchAdminSocialConnections,
  fetchAdminSubscriptions,
  deleteAdminSocialConnection,
  saveAdminSocialConnection,
  updateAdminBillingPricing,
  updateAdminSubscription,
  verifyAdminAccess,
} from "../../lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

const SOCIAL_PLATFORM_OPTIONS = [
  { key: "youtube", label: "YouTube" },
  { key: "instagram", label: "Instagram" },
  { key: "facebook", label: "Facebook" },
  { key: "x", label: "X" },
  { key: "tiktok", label: "TikTok" },
] as const;

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
  factory_one_time_price_usd: number;
  factory_one_time_stripe_price_id: string;
  factory_subscription_price_usd: number;
  factory_subscription_stripe_price_id: string;
  owner_mode_enabled: boolean;
  receipts_live_mode: boolean;
  free_base_character_slots: number;
  character_slot_addon_size: number;
  character_slot_addon_cost_credits: number;
};

type FactoryModeAccess = "none" | "one_time" | "subscription";

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
  factory_one_time_price_usd: 149,
  factory_one_time_stripe_price_id: "",
  factory_subscription_price_usd: 39,
  factory_subscription_stripe_price_id: "",
  owner_mode_enabled: false,
  receipts_live_mode: false,
  free_base_character_slots: 5,
  character_slot_addon_size: 5,
  character_slot_addon_cost_credits: 50,
};

function pricingFormFromSettings(settings: BillingPricingSettings): BillingPricingForm {
  const moderate = settings.plans.find((plan) => plan.id === "moderate");
  const pro = settings.plans.find((plan) => plan.id === "pro");
  const studio = settings.plans.find((plan) => plan.id === "studio");
  const factoryOneTime = settings.plans.find((plan) => plan.id === "factory_one_time");
  const factorySubscription = settings.plans.find((plan) => plan.id === "factory_subscription");
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
    factory_one_time_price_usd:
      factoryOneTime?.price_usd ?? DEFAULT_PRICING_FORM.factory_one_time_price_usd,
    factory_one_time_stripe_price_id: factoryOneTime?.stripe_price_id ?? "",
    factory_subscription_price_usd:
      factorySubscription?.price_usd ?? DEFAULT_PRICING_FORM.factory_subscription_price_usd,
    factory_subscription_stripe_price_id: factorySubscription?.stripe_price_id ?? "",
    owner_mode_enabled: settings.owner_mode_enabled ?? DEFAULT_PRICING_FORM.owner_mode_enabled,
    receipts_live_mode: settings.receipts_live_mode ?? DEFAULT_PRICING_FORM.receipts_live_mode,
    free_base_character_slots: settings.free_base_character_slots,
    character_slot_addon_size: settings.character_slot_addon_size,
    character_slot_addon_cost_credits: settings.character_slot_addon_cost_credits,
  };
}

function socialFormFromConnection(connection: SocialAccountConnection | null) {
  return {
    selectedSocialConnectionId: connection?.connection_id ?? null,
    socialPlatform: (connection?.platform as SocialAccountConnection["platform"]) ?? "youtube",
    socialAccountLabel: connection?.account_label ?? "",
    socialAccountIdentifier: connection?.account_identifier ?? "",
    socialAccessToken: "",
    socialAccessTokenSecret: "",
    socialRefreshToken: "",
    socialClientKey: "",
    socialClientSecret: "",
    socialTokenExpiresAt: connection?.token_expires_at ? connection.token_expires_at.slice(0, 16) : "",
    socialEnabled: connection?.enabled ?? true,
  };
}

export default function AdminPage() {
  const [hasMounted, setHasMounted] = useState(false);
  const [gateLoading, setGateLoading] = useState(true);
  const [gateError, setGateError] = useState<string | null>(null);
  const [ownerAuthenticated, setOwnerAuthenticated] = useState(false);
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [showOwnerPassword, setShowOwnerPassword] = useState(false);
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
  const [factoryModeAccess, setFactoryModeAccess] = useState<FactoryModeAccess>("none");
  const [factoryModeRenewalDate, setFactoryModeRenewalDate] = useState("");
  const [pricingForm, setPricingForm] = useState<BillingPricingForm>(DEFAULT_PRICING_FORM);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [userActionBusy, setUserActionBusy] = useState<string | null>(null);
  const [socialConnections, setSocialConnections] = useState<SocialAccountConnection[]>([]);
  const [selectedSocialConnectionId, setSelectedSocialConnectionId] = useState<string | null>(null);
  const [socialPlatform, setSocialPlatform] = useState<SocialAccountConnection["platform"]>("youtube");
  const [socialAccountLabel, setSocialAccountLabel] = useState("");
  const [socialAccountIdentifier, setSocialAccountIdentifier] = useState("");
  const [socialAccessToken, setSocialAccessToken] = useState("");
  const [socialAccessTokenSecret, setSocialAccessTokenSecret] = useState("");
  const [socialRefreshToken, setSocialRefreshToken] = useState("");
  const [socialClientKey, setSocialClientKey] = useState("");
  const [socialClientSecret, setSocialClientSecret] = useState("");
  const [socialTokenExpiresAt, setSocialTokenExpiresAt] = useState("");
  const [socialEnabled, setSocialEnabled] = useState(true);
  const [socialLoading, setSocialLoading] = useState(false);
  const [socialSaving, setSocialSaving] = useState(false);
  const [socialRemovingId, setSocialRemovingId] = useState<string | null>(null);
  const [socialError, setSocialError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [visitAnalytics, setVisitAnalytics] = useState<VisitAnalyticsSummary | null>(null);
  const [visitAnalyticsLoading, setVisitAnalyticsLoading] = useState(false);
  const [visitAnalyticsError, setVisitAnalyticsError] = useState<string | null>(null);
  const socialSelectedIdRef = useRef<string | null>(null);

  const syncOwnerModeSessionFlag = useCallback((enabled: boolean) => {
    if (typeof window === "undefined") {
      return;
    }
    if (enabled) {
      window.sessionStorage.setItem("pc_owner_mode_enabled", "true");
    } else {
      window.sessionStorage.removeItem("pc_owner_mode_enabled");
    }
  }, []);

  const selectedSubscription = useMemo(
    () => items.find((item) => item.email === selectedEmail) ?? items[0] ?? null,
    [items, selectedEmail]
  );

  useEffect(() => {
    setHasMounted(true);
  }, []);

  useEffect(() => {
    if (!hasMounted) {
      return;
    }
    let active = true;
    const token = window.localStorage.getItem("pc_token");
    if (!token) {
      setOwnerAuthenticated(false);
      setHasAdminAccess(false);
      setGateLoading(false);
      return;
    }

    setGateLoading(true);
    globalThis.fetch(`${API_BASE}/auth/me`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Owner authentication required");
        }
        const user = await response.json();
        if (user.role !== "admin") {
          throw new Error("This account is not authorized for owner administration");
        }
        if (!active) return;
        setOwnerAuthenticated(true);
        const adminToken =
          window.sessionStorage.getItem("pc_admin_access_token") ??
          window.localStorage.getItem("pc_admin_access_token");
        setHasAdminAccess(Boolean(adminToken));
      })
      .catch((err) => {
        if (!active) return;
        setOwnerAuthenticated(false);
        setHasAdminAccess(false);
        setGateError(err instanceof Error ? err.message : "Owner authentication required");
      })
      .finally(() => {
        if (active) setGateLoading(false);
      });

    return () => {
      active = false;
    };
  }, [hasMounted]);

  useEffect(() => {
    if (!ownerAuthenticated) {
      return;
    }
    let active = true;
    setGateLoading(true);
    setGateError(null);
    fetchAdmin2FAStatus()
      .then((statusResponse) => {
        if (!active) return;
        setTwoFaEnabled(Boolean(statusResponse.enabled));
        setTwoFaDetail(statusResponse.detail ?? null);
      })
      .catch((err) => {
        if (active) {
          setGateError(err instanceof Error ? err.message : "Failed to load admin access");
        }
      })
      .finally(() => {
        if (active) setGateLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ownerAuthenticated]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSocialLoading(true);
    setSocialError(null);
    try {
      const [subscriptionResponse, pricingResponse, socialResponse] = await Promise.all([
        fetchAdminSubscriptions(),
        fetchAdminBillingPricing(),
        fetchAdminSocialConnections(),
      ]);
      setItems(subscriptionResponse.items);
      setPricingForm(pricingFormFromSettings(pricingResponse));
      syncOwnerModeSessionFlag(Boolean(pricingResponse.owner_mode_enabled));
      setSocialConnections(socialResponse.items);
      if (!selectedEmail && subscriptionResponse.items.length > 0) {
        setSelectedEmail(subscriptionResponse.items[0].email);
      }
      const currentSocialId = socialSelectedIdRef.current;
      const nextSelectedConnection =
        socialResponse.items.find((connection) => connection.connection_id === currentSocialId) ??
        socialResponse.items[0] ??
        null;
      if (nextSelectedConnection) {
        handleSelectSocialConnection(nextSelectedConnection);
      } else if (currentSocialId !== null) {
        handleSelectSocialConnection(null);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load admin data";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setLoading(false);
      setSocialLoading(false);
    }
  }, [selectedEmail, syncOwnerModeSessionFlag]);

  useEffect(() => {
    if (hasAdminAccess) {
      load();
    }
  }, [hasAdminAccess, load]);

  useEffect(() => {
    if (!hasAdminAccess) {
      setVisitAnalytics(null);
      setVisitAnalyticsLoading(false);
      return;
    }
    let active = true;
    setVisitAnalyticsLoading(true);
    setVisitAnalyticsError(null);
    fetchAdminVisitAnalyticsSummary()
      .then((summary) => {
        if (active) {
          setVisitAnalytics(summary);
        }
      })
      .catch((err) => {
        if (active) {
          setVisitAnalyticsError(err instanceof Error ? err.message : "Failed to load visitor analytics");
        }
      })
      .finally(() => {
        if (active) {
          setVisitAnalyticsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [hasAdminAccess]);

  useEffect(() => {
    if (!selectedSubscription) {
      return;
    }
    setPlanName(selectedSubscription.plan_name);
    setStatus(selectedSubscription.status);
    setFactoryModeAccess(
      (selectedSubscription.factory_mode_access as FactoryModeAccess | undefined) ?? "none"
    );
    setFactoryModeRenewalDate(
      selectedSubscription.factory_mode_renewal_date
        ? selectedSubscription.factory_mode_renewal_date.slice(0, 16)
        : ""
    );
  }, [selectedSubscription]);

  const handleOwnerLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setGateError(null);
    if (!ownerEmail.trim() || !ownerPassword) {
      setGateError("Enter the owner email and password.");
      return;
    }
    setGateLoading(true);
    try {
      const response = await globalThis.fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: ownerEmail.trim(), password: ownerPassword }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? "Invalid owner credentials");
      }
      const data = await response.json();
      window.localStorage.setItem("pc_token", data.access_token);

      const meResponse = await globalThis.fetch(`${API_BASE}/auth/me`, {
        cache: "no-store",
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      const me = await meResponse.json().catch(() => null);
      if (!meResponse.ok || me?.role !== "admin") {
        window.localStorage.removeItem("pc_token");
        throw new Error("This account is not authorized for owner administration");
      }

      setOwnerAuthenticated(true);
      setOwnerPassword("");
      setHasAdminAccess(false);
    } catch (err) {
      setGateError(err instanceof Error ? err.message : "Owner authentication failed");
    } finally {
      setGateLoading(false);
    }
  };

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
      window.localStorage.removeItem("pc_admin_access_token");
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
    window.localStorage.removeItem("pc_admin_access_token");
    window.sessionStorage.removeItem("pc_owner_mode_enabled");
    setHasAdminAccess(false);
    setItems([]);
    setActionMessage(null);
    setUserActionBusy(null);
  };

  const isInvalidAdminAccessTokenError = useCallback((message: string | null | undefined) => {
    const normalized = (message ?? "").toLowerCase();
    return (
      normalized.includes("invalid admin access token") ||
      normalized.includes("admin access token does not match user") ||
      normalized.includes("missing admin access token")
    );
  }, []);

  const invalidateAdminAccess = useCallback(
    (message: string) => {
      handleLock();
      setGateError(message);
    },
    [handleLock]
  );

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
        factory_mode_access: factoryModeAccess,
        factory_mode_renewal_date:
          factoryModeAccess === "subscription" && factoryModeRenewalDate
            ? new Date(factoryModeRenewalDate).toISOString()
            : null,
      });
      await load();
      setCreditsDelta(0);
      setActionMessage(`Updated ${selectedEmail}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update subscription";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleModerateUser = async (email: string, nextStatus: string) => {
    setUserActionBusy(`${email}:${nextStatus}`);
    setError(null);
    setActionMessage(null);
    try {
      await updateAdminSubscription(email, { status: nextStatus });
      await load();
      setActionMessage(`${email} set to ${nextStatus}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update user status";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setUserActionBusy(null);
    }
  };

  const handleDeleteUser = async (email: string) => {
    if (typeof window !== "undefined" && !window.confirm(`Delete ${email}?`)) {
      return;
    }
    setUserActionBusy(`${email}:delete`);
    setError(null);
    setActionMessage(null);
    try {
      await deleteAdminUser(email);
      await load();
      setActionMessage(`${email} deleted.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete user";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setUserActionBusy(null);
    }
  };

  const suspendActionForStatus = (currentStatus: string) => ({
    label: currentStatus === "suspended" ? "Unsuspend" : "Suspend",
    nextStatus: currentStatus === "suspended" ? "active" : "suspended",
  });

  const banActionForStatus = (currentStatus: string) => ({
    label: currentStatus === "banned" ? "Unban" : "Ban",
    nextStatus: currentStatus === "banned" ? "active" : "banned",
  });

  const handleClearTestPurchases = async () => {
    if (typeof window !== "undefined" && !window.confirm("Delete all test purchases?")) {
      return;
    }
    setUserActionBusy("test-purge");
    setError(null);
    setActionMessage(null);
    try {
      const result = await clearAdminTestPurchases();
      await load();
      setActionMessage(`Deleted ${result.deleted_count} test purchase(s).`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to clear test purchases";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setUserActionBusy(null);
    }
  };

  const handleClearTransactionRecords = async () => {
    if (typeof window !== "undefined" && !window.confirm("Delete all test transaction records?")) {
      return;
    }
    setUserActionBusy("transaction-purge");
    setError(null);
    setActionMessage(null);
    try {
      const result = await clearBillingTransactionRecords();
      await load();
      setActionMessage(`Deleted ${result.deleted_count} test transaction record${result.deleted_count === 1 ? "" : "s"}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to clear transaction records";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setError(message);
    } finally {
      setUserActionBusy(null);
    }
  };

  const handlePricingUpdate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await persistPricingSettings(pricingForm);
  };

  const persistPricingSettings = useCallback(
    async (nextForm: BillingPricingForm) => {
      setPricingLoading(true);
      setError(null);
      try {
        const response = await updateAdminBillingPricing({
          ...nextForm,
          moderate_stripe_price_id: nextForm.moderate_stripe_price_id || undefined,
          pro_stripe_price_id: nextForm.pro_stripe_price_id || undefined,
          studio_stripe_price_id: nextForm.studio_stripe_price_id || undefined,
          factory_one_time_stripe_price_id: nextForm.factory_one_time_stripe_price_id || undefined,
          factory_subscription_stripe_price_id:
            nextForm.factory_subscription_stripe_price_id || undefined,
          owner_mode_enabled: nextForm.owner_mode_enabled,
          receipts_live_mode: nextForm.receipts_live_mode,
          free_base_character_slots: nextForm.free_base_character_slots,
          character_slot_addon_size: nextForm.character_slot_addon_size,
          character_slot_addon_cost_credits: nextForm.character_slot_addon_cost_credits,
        });
        setPricingForm(pricingFormFromSettings(response));
        syncOwnerModeSessionFlag(Boolean(response.owner_mode_enabled));
        return response;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to update pricing";
        if (isInvalidAdminAccessTokenError(message)) {
          invalidateAdminAccess("Admin session expired. Unlock again.");
          return null;
        }
        setError(message);
        return null;
      } finally {
        setPricingLoading(false);
      }
    },
    [invalidateAdminAccess, isInvalidAdminAccessTokenError, syncOwnerModeSessionFlag]
  );

  const handleSelectSocialConnection = (connection: SocialAccountConnection | null) => {
    socialSelectedIdRef.current = connection?.connection_id ?? null;
    const form = socialFormFromConnection(connection);
    setSelectedSocialConnectionId(form.selectedSocialConnectionId);
    setSocialPlatform(form.socialPlatform);
    setSocialAccountLabel(form.socialAccountLabel);
    setSocialAccountIdentifier(form.socialAccountIdentifier);
    setSocialAccessToken(form.socialAccessToken);
    setSocialAccessTokenSecret(form.socialAccessTokenSecret);
    setSocialRefreshToken(form.socialRefreshToken);
    setSocialClientKey(form.socialClientKey);
    setSocialClientSecret(form.socialClientSecret);
    setSocialTokenExpiresAt(form.socialTokenExpiresAt);
    setSocialEnabled(form.socialEnabled);
  };

  const resetSocialConnectionForm = () => {
    handleSelectSocialConnection(null);
  };

  const handleSaveSocialConnection = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSocialSaving(true);
    setSocialError(null);
    try {
      if (!socialAccountLabel.trim()) {
        throw new Error("Enter a shared account label.");
      }
      const connection = await saveAdminSocialConnection({
        connection_id: selectedSocialConnectionId,
        platform: socialPlatform,
        account_label: socialAccountLabel.trim(),
        account_identifier: socialAccountIdentifier.trim() || null,
        access_token: socialAccessToken.trim() || undefined,
        access_token_secret: socialAccessTokenSecret.trim() || undefined,
        refresh_token: socialRefreshToken.trim() || undefined,
        client_key: socialClientKey.trim() || undefined,
        client_secret: socialClientSecret.trim() || undefined,
        token_expires_at: socialTokenExpiresAt ? new Date(socialTokenExpiresAt).toISOString() : undefined,
        enabled: socialEnabled,
      });
      await load();
      handleSelectSocialConnection(connection);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save social credential";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setSocialError(message);
    } finally {
      setSocialSaving(false);
    }
  };

  const handleDeleteSocialConnection = async (connectionId: string) => {
    setSocialRemovingId(connectionId);
    setSocialError(null);
    try {
      await deleteAdminSocialConnection(connectionId);
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete social credential";
      if (isInvalidAdminAccessTokenError(message)) {
        invalidateAdminAccess("Admin session expired. Unlock again.");
        return;
      }
      setSocialError(message);
    } finally {
      setSocialRemovingId(null);
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
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
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
      ) : !ownerAuthenticated ? (
        <main className="mx-auto max-w-3xl px-6 py-10">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-6">
            <h2 className="text-2xl font-bold text-white">Owner Access</h2>
            <p className="mt-2 text-sm text-slate-300">
              Authenticate with the private owner account before the administrative security gate is shown.
            </p>
            <form className="mt-6 space-y-3" onSubmit={handleOwnerLogin}>
              <div>
                <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="owner-email">
                  Owner email
                </label>
                <input
                  id="owner-email"
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                  type="email"
                  value={ownerEmail}
                  onChange={(event) => setOwnerEmail(event.target.value)}
                  autoComplete="username"
                  required
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wide text-slate-400" htmlFor="owner-password">
                  Owner password
                </label>
                <div className="relative mt-2">
                  <input
                    id="owner-password"
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 pr-20 text-sm text-white"
                    type={showOwnerPassword ? "text" : "password"}
                    value={ownerPassword}
                    onChange={(event) => setOwnerPassword(event.target.value)}
                    autoComplete="current-password"
                    required
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 right-3 text-xs text-slate-400"
                    onClick={() => setShowOwnerPassword((value) => !value)}
                  >
                    {showOwnerPassword ? "Hide" : "Show"}
                  </button>
                </div>
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
                {gateLoading ? "Authenticating..." : "Continue to owner security gate"}
              </button>
            </form>
          </section>
        </main>
      ) : !hasAdminAccess ? (
        <main className="mx-auto max-w-3xl px-6 py-10">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-6">
            <h2 className="text-2xl font-bold text-white">Admin Security Gate</h2>
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
        <main className="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:h-[calc(100vh-5rem)] lg:grid-cols-[1.4fr_0.9fr] lg:overflow-hidden">
          <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 lg:flex lg:min-h-0 lg:flex-col lg:overflow-y-auto">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Users and Credits</h2>
                <p className="text-xs text-slate-400">{subtitle}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-200"
                  onClick={handleLock}
                >
                  Lock
                </button>
                <button
                  type="button"
                  className="rounded-full border border-rose-400/30 bg-rose-500/10 px-3 py-1 text-[11px] font-semibold text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleClearTransactionRecords()}
                  disabled={userActionBusy === "transaction-purge"}
                >
                  {userActionBusy === "transaction-purge" ? "Clearing..." : "Clear test records"}
                </button>
                <button
                  type="button"
                  className="rounded-full border border-red-400/30 bg-red-500/10 px-3 py-1 text-[11px] font-semibold text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleClearTestPurchases()}
                  disabled={userActionBusy === "test-purge"}
                >
                  {userActionBusy === "test-purge" ? "Clearing..." : "Clear test purchases"}
                </button>
              </div>
            </div>
            {error ? (
              <p className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                {error}
              </p>
            ) : null}
            {actionMessage ? (
              <p className="mt-3 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
                {actionMessage}
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
                    <th className="px-2 py-2">Actions</th>
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
                      <td className="px-2 py-2">
                        <div className="flex flex-wrap gap-2">
                          {(() => {
                            const suspendAction = suspendActionForStatus(item.status);
                            return (
                              <button
                                type="button"
                                className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                disabled={userActionBusy !== null}
                                onClick={() => void handleModerateUser(item.email, suspendAction.nextStatus)}
                              >
                                {suspendAction.label}
                              </button>
                            );
                          })()}
                          {(() => {
                            const banAction = banActionForStatus(item.status);
                            return (
                              <button
                                type="button"
                                className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                disabled={userActionBusy !== null}
                                onClick={() => void handleModerateUser(item.email, banAction.nextStatus)}
                              >
                                {banAction.label}
                              </button>
                            );
                          })()}
                          <button
                            type="button"
                            className="rounded-full border border-red-400/30 bg-red-500/10 px-2 py-1 text-[10px] font-semibold text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                            disabled={userActionBusy !== null}
                            onClick={() => void handleDeleteUser(item.email)}
                          >
                            {userActionBusy === `${item.email}:delete` ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-4 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
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
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">Visitor Analytics</h2>
                  <p className="mt-2 text-sm text-slate-400">
                    Track humans, bots, top paths, recency, and daily traffic from the live app.
                  </p>
                </div>
                <span className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                  Live
                </span>
              </div>
              {visitAnalyticsError ? (
                <p className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                  {visitAnalyticsError}
                </p>
              ) : null}
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Total visits", visitAnalytics?.total_visits ?? 0],
                  ["Human visits", visitAnalytics?.human_visits ?? 0],
                  ["Bot visits", visitAnalytics?.bot_visits ?? 0],
                  ["Sessions", visitAnalytics?.unique_sessions ?? 0],
                  ["Unique paths", visitAnalytics?.unique_paths ?? 0],
                  ["Last 24h", visitAnalytics?.visits_last_24h ?? 0],
                  ["Last 7d", visitAnalytics?.visits_last_7d ?? 0],
                  ["Daily points", visitAnalytics?.daily_visits.length ?? 0],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label as string}</p>
                    <p className="mt-2 text-2xl font-semibold text-white">{String(value)}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Top paths</p>
                  <div className="mt-3 space-y-2">
                    {visitAnalyticsLoading ? (
                      <p className="text-sm text-slate-400">Loading analytics...</p>
                    ) : visitAnalytics?.top_paths.length ? (
                      visitAnalytics.top_paths.map((item) => (
                        <div key={item.path} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                          <div className="flex items-center justify-between gap-3">
                            <p className="truncate text-sm font-medium text-white">{item.path}</p>
                            <p className="text-xs text-slate-400">{item.visits} visits</p>
                          </div>
                          <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Human {item.human_visits} / Bot {item.bot_visits}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">No visits recorded yet.</p>
                    )}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Recent visits</p>
                  <div className="mt-3 space-y-2">
                    {visitAnalytics?.recent_visits.length ? (
                      visitAnalytics.recent_visits.map((item) => (
                        <div key={item.visit_id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-medium text-white">{item.path}</p>
                            <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                              {new Date(item.created_at).toLocaleString()}
                            </p>
                          </div>
                          <p className="mt-1 text-xs text-slate-400">
                            {item.is_bot ? `Bot · ${item.bot_reason ?? "detected"}` : "Human"} · {item.event_type}
                            {item.device_type ? ` · ${item.device_type}` : ""}
                            {item.country_code ? ` · ${item.country_code}` : ""}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">No recent visits yet.</p>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Top devices</p>
                  <div className="mt-3 space-y-2">
                    {visitAnalytics?.top_devices.length ? (
                      visitAnalytics.top_devices.map((item) => (
                        <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                          <div className="flex items-center justify-between gap-3">
                            <p className="truncate text-sm font-medium text-white">{item.label}</p>
                            <p className="text-xs text-slate-400">{item.visits} visits</p>
                          </div>
                          <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Human {item.human_visits} / Bot {item.bot_visits}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">No device breakdown yet.</p>
                    )}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Top countries</p>
                  <div className="mt-3 space-y-2">
                    {visitAnalytics?.top_countries.length ? (
                      visitAnalytics.top_countries.map((item) => (
                        <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                          <div className="flex items-center justify-between gap-3">
                            <p className="truncate text-sm font-medium text-white">{item.label}</p>
                            <p className="text-xs text-slate-400">{item.visits} visits</p>
                          </div>
                          <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Human {item.human_visits} / Bot {item.bot_visits}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">No country breakdown yet.</p>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Daily visits</p>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {visitAnalytics?.daily_visits.length ?? 0} points
                  </p>
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  {visitAnalytics?.daily_visits.length ? (
                    visitAnalytics.daily_visits.map((point) => (
                      <div key={point.day} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                        <p className="text-sm font-medium text-white">
                          {new Date(`${point.day}T00:00:00Z`).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          {point.visits} total · {point.human_visits} human · {point.bot_visits} bot
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-400">No daily visit history yet.</p>
                  )}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">Social Publishing Credentials</h2>
                  <p className="mt-2 text-sm text-slate-400">
                    Shared platform secrets live here. Public users only see labels and identifiers.
                  </p>
                </div>
                <button
                  className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-200"
                  type="button"
                  onClick={resetSocialConnectionForm}
                >
                  New
                </button>
              </div>
              {socialError ? (
                <p className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                  {socialError}
                </p>
              ) : null}
              <div className="mt-4 grid gap-3">
                {socialConnections.length > 0 ? (
                  socialConnections.map((connection) => {
                    const selected = selectedSocialConnectionId === connection.connection_id;
                    return (
                      <div
                        key={connection.connection_id}
                        className={`rounded-2xl border p-4 ${
                          selected ? "border-aurora/50 bg-aurora/10" : "border-slate-800 bg-slate-900/50"
                        }`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-white">{connection.account_label}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.25em] text-slate-500">
                              {socialPlatformLabel(connection.platform)}
                            </p>
                            <p className="mt-2 text-sm text-slate-400">
                              {connection.account_identifier || "No identifier"}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-200"
                              type="button"
                              onClick={() => handleSelectSocialConnection(connection)}
                            >
                              Edit
                            </button>
                            <button
                              className="rounded-full border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                              type="button"
                              disabled={socialRemovingId === connection.connection_id}
                              onClick={() => void handleDeleteSocialConnection(connection.connection_id)}
                            >
                              {socialRemovingId === connection.connection_id ? "Removing..." : "Remove"}
                            </button>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                          <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2 py-1">
                            {connection.enabled ? "Ready" : "Disabled"}
                          </span>
                          {selected ? (
                            <span className="rounded-full border border-aurora/40 bg-aurora/10 px-2 py-1 text-aurora">
                              Selected
                            </span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-4 text-sm text-slate-400">
                    No shared social credentials have been saved yet.
                  </div>
                )}
              </div>
              <form className="mt-5 space-y-4" onSubmit={handleSaveSocialConnection}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Platform</span>
                    <select
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                      value={socialPlatform}
                      onChange={(event) => setSocialPlatform(event.target.value as SocialAccountConnection["platform"])}
                    >
                      {SOCIAL_PLATFORM_OPTIONS.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Account label</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialAccountLabel}
                      onChange={(event) => setSocialAccountLabel(event.target.value)}
                      placeholder="My Main Channel"
                    />
                  </label>
                </div>
                <label className="grid gap-2 text-sm text-slate-200">
                  <span className="text-xs uppercase tracking-wide text-slate-400">
                    {socialPlatformIdentifierLabel(socialPlatform)}
                  </span>
                  <input
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                    value={socialAccountIdentifier}
                    onChange={(event) => setSocialAccountIdentifier(event.target.value)}
                    placeholder="Account identifier"
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Access token</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialAccessToken}
                      onChange={(event) => setSocialAccessToken(event.target.value)}
                      placeholder="Stored securely"
                    />
                  </label>
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Token secret</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialAccessTokenSecret}
                      onChange={(event) => setSocialAccessTokenSecret(event.target.value)}
                      placeholder="Stored securely"
                    />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Refresh token</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialRefreshToken}
                      onChange={(event) => setSocialRefreshToken(event.target.value)}
                      placeholder="Stored securely"
                    />
                  </label>
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Client key</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialClientKey}
                      onChange={(event) => setSocialClientKey(event.target.value)}
                      placeholder="Stored securely"
                    />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Client secret</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                      value={socialClientSecret}
                      onChange={(event) => setSocialClientSecret(event.target.value)}
                      placeholder="Stored securely"
                    />
                  </label>
                  <label className="grid gap-2 text-sm text-slate-200">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Token expiry</span>
                    <input
                      className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                      type="datetime-local"
                      value={socialTokenExpiresAt}
                      onChange={(event) => setSocialTokenExpiresAt(event.target.value)}
                    />
                  </label>
                </div>
                <label className="flex items-center gap-3 text-sm text-slate-200">
                  <input
                    className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-aurora"
                    type="checkbox"
                    checked={socialEnabled}
                    onChange={(event) => setSocialEnabled(event.target.checked)}
                  />
                  Enabled
                </label>
                <p className="text-xs text-slate-500">
                  Leave any secret field blank to keep the existing stored value.
                </p>
                <button
                  className="w-full rounded-lg border border-aurora/40 bg-aurora/10 px-3 py-2 text-sm font-semibold text-aurora"
                  type="submit"
                  disabled={socialSaving || socialLoading}
                >
                  {socialSaving ? "Saving..." : "Save shared credential"}
                </button>
              </form>
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
                    <option value="suspended">suspended</option>
                    <option value="banned">banned</option>
                    <option value="paused">paused</option>
                    <option value="canceled">canceled</option>
                  </select>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-400">Factory Mode</p>
                      <p className="mt-1 text-sm text-slate-300">
                        Unlock or revoke autonomous access for this user.
                      </p>
                    </div>
                    <span className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                      {factoryModeAccess === "none"
                        ? "Locked"
                        : factoryModeAccess === "subscription"
                          ? "Subscription"
                          : "One-Time"}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {[
                      ["none", "Locked"],
                      ["one_time", "One-Time"],
                      ["subscription", "Subscription"],
                    ].map(([value, label]) => {
                      const selected = factoryModeAccess === value;
                      return (
                        <button
                          key={value}
                          type="button"
                          aria-label={`Factory Mode ${label}`}
                          className={`rounded-xl border px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] transition ${
                            selected
                              ? "border-aurora/50 bg-aurora/15 text-aurora"
                              : "border-slate-800 bg-slate-950/70 text-slate-400"
                          }`}
                          aria-pressed={selected}
                          onClick={() => setFactoryModeAccess(value as FactoryModeAccess)}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  {factoryModeAccess === "subscription" ? (
                    <label className="mt-3 grid gap-2 text-sm text-slate-200">
                      <span className="text-xs uppercase tracking-wide text-slate-400">
                        Renewal date
                      </span>
                      <input
                        className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                        type="datetime-local"
                        value={factoryModeRenewalDate}
                        onChange={(event) => setFactoryModeRenewalDate(event.target.value)}
                      />
                    </label>
                  ) : null}
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

                <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                  <p className="text-sm font-semibold text-white">Factory Mode Access</p>
                  <p className="mt-1 text-xs text-slate-400">
                    Edit the one-time and subscription prices used for Factory Mode checkout.
                  </p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                      One-Time Price USD
                      <input
                        className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                        type="number"
                        value={pricingForm.factory_one_time_price_usd}
                        onChange={(event) =>
                          setPricingForm((current) => ({
                            ...current,
                            factory_one_time_price_usd: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                      One-Time Stripe Price ID
                      <input
                        className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                        value={pricingForm.factory_one_time_stripe_price_id}
                        onChange={(event) =>
                          setPricingForm((current) => ({
                            ...current,
                            factory_one_time_stripe_price_id: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                      Subscription Price USD
                      <input
                        className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                        type="number"
                        value={pricingForm.factory_subscription_price_usd}
                        onChange={(event) =>
                          setPricingForm((current) => ({
                            ...current,
                            factory_subscription_price_usd: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                    <label className="text-xs uppercase tracking-wide text-slate-400">
                      Subscription Stripe Price ID
                      <input
                        className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                        value={pricingForm.factory_subscription_stripe_price_id}
                        onChange={(event) =>
                          setPricingForm((current) => ({
                            ...current,
                            factory_subscription_stripe_price_id: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-white">Owner Mode</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Bypass all gated features for the owner account during testing and diagnostics.
                      </p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-label="Owner mode"
                      aria-checked={pricingForm.owner_mode_enabled}
                      onClick={() => {
                        const nextForm = {
                          ...pricingForm,
                          owner_mode_enabled: !pricingForm.owner_mode_enabled,
                        };
                        setPricingForm(nextForm);
                        void persistPricingSettings(nextForm);
                      }}
                      className={`relative inline-flex h-9 w-24 items-center rounded-full border px-1 transition ${
                        pricingForm.owner_mode_enabled
                          ? "border-emerald-500/60 bg-emerald-500/20"
                          : "border-slate-700 bg-slate-900/60"
                      }`}
                    >
                      <span
                        className={`inline-flex h-7 w-10 items-center justify-center rounded-full text-[11px] font-semibold uppercase tracking-[0.25em] transition ${
                          pricingForm.owner_mode_enabled
                            ? "translate-x-10 bg-emerald-500 text-slate-950"
                            : "translate-x-0 bg-slate-700 text-slate-200"
                        }`}
                      >
                        {pricingForm.owner_mode_enabled ? "On" : "Off"}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-white">Receipt mode</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Test mode deletes receipts completely. Live mode keeps audit copies.
                      </p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-label="Receipt mode"
                      aria-checked={pricingForm.receipts_live_mode}
                      onClick={() =>
                        setPricingForm((current) => ({
                          ...current,
                          receipts_live_mode: !current.receipts_live_mode,
                        }))
                      }
                      className={`relative inline-flex h-9 w-24 items-center rounded-full border px-1 transition ${
                        pricingForm.receipts_live_mode
                          ? "border-emerald-500/60 bg-emerald-500/20"
                          : "border-amber-500/60 bg-amber-500/20"
                      }`}
                    >
                      <span
                        className={`inline-flex h-7 w-10 items-center justify-center rounded-full text-[11px] font-semibold uppercase tracking-[0.25em] transition ${
                          pricingForm.receipts_live_mode
                            ? "translate-x-10 bg-emerald-500 text-slate-950"
                            : "translate-x-0 bg-amber-500 text-slate-950"
                        }`}
                      >
                        {pricingForm.receipts_live_mode ? "Live" : "Test"}
                      </span>
                    </button>
                  </div>
                </div>

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
