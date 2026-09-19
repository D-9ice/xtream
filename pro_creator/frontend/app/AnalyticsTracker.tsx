"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { recordAnalyticsVisit } from "../lib/api";

const VISIT_SESSION_COOKIE = "pc_visit_session";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  if (!match) return null;
  const [, value] = match.split("=", 2);
  return value ? decodeURIComponent(value) : null;
}

function getOrCreateSessionId(): string {
  const existingCookie = getCookie(VISIT_SESSION_COOKIE);
  if (existingCookie) return existingCookie;

  const nextSession =
    globalThis.crypto?.randomUUID?.() ??
    `visit-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  if (typeof document !== "undefined") {
    document.cookie = `${VISIT_SESSION_COOKIE}=${encodeURIComponent(
      nextSession
    )}; path=/; max-age=31536000; samesite=lax`;
  }
  return nextSession;
}

function detectDeviceHint(): string {
  if (typeof navigator === "undefined") return "unknown";
  const userAgentData = (navigator as Navigator & {
    userAgentData?: { mobile?: boolean };
  }).userAgentData;
  const ua = navigator.userAgent.toLowerCase();
  if (
    ua.includes("ipad") ||
    ua.includes("tablet") ||
    ua.includes("kindle") ||
    ua.includes("silk")
  ) {
    return "tablet";
  }
  if (
    userAgentData?.mobile ||
    ua.includes("android") ||
    ua.includes("iphone") ||
    ua.includes("mobile")
  ) {
    return "mobile";
  }
  return "desktop";
}

function detectCountryHint(): string | null {
  if (typeof navigator === "undefined") return null;
  const locale = navigator.language || navigator.languages?.[0] || "";
  const match = locale.match(/[-_](?<country>[A-Za-z]{2})$/);
  return match?.groups?.country?.toUpperCase() ?? null;
}

function tokenRole(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = JSON.parse(globalThis.atob(padded)) as { role?: unknown };
    return typeof decoded.role === "string" ? decoded.role.toLowerCase() : null;
  } catch {
    return null;
  }
}

function shouldExcludeFromPublicAnalytics(pathname: string): boolean {
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    return true;
  }
  if (typeof window === "undefined") {
    return false;
  }
  if (window.sessionStorage.getItem("pc_owner_mode_enabled") === "true") {
    return true;
  }
  return tokenRole(window.localStorage.getItem("pc_token")) === "admin";
}

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const lastRecordedPath = useRef<string | null>(null);

  useEffect(() => {
    if (shouldExcludeFromPublicAnalytics(pathname)) {
      return;
    }

    const path = search ? `${pathname}?${search}` : pathname;
    if (lastRecordedPath.current === path) {
      return;
    }

    const eventType = lastRecordedPath.current === null ? "page_view" : "route_change";
    lastRecordedPath.current = path;

    void recordAnalyticsVisit({
      path,
      referrer: document.referrer || null,
      user_agent: navigator.userAgent,
      device_hint: detectDeviceHint(),
      country_hint: detectCountryHint(),
      page_title: document.title,
      session_id: getOrCreateSessionId(),
      event_type: eventType,
      bot_hint: false,
    }).catch(() => undefined);
  }, [pathname, search]);

  return null;
}
