"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { recordAnalyticsVisit } from "../lib/api";

const VISIT_SESSION_COOKIE = "pc_visit_session";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  if (!match) {
    return null;
  }
  const [, value] = match.split("=", 2);
  return value ? decodeURIComponent(value) : null;
}

function getOrCreateSessionId(): string {
  const existingCookie = getCookie(VISIT_SESSION_COOKIE);
  if (existingCookie) {
    return existingCookie;
  }
  const nextSession = globalThis.crypto?.randomUUID?.() ?? `visit-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  if (typeof document !== "undefined") {
    document.cookie = `${VISIT_SESSION_COOKIE}=${encodeURIComponent(nextSession)}; path=/; max-age=31536000; samesite=lax`;
  }
  return nextSession;
}

function detectDeviceHint(): string {
  if (typeof navigator === "undefined") {
    return "unknown";
  }
  const userAgentData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("ipad") || ua.includes("tablet") || ua.includes("kindle") || ua.includes("silk")) {
    return "tablet";
  }
  if (userAgentData?.mobile || ua.includes("android") || ua.includes("iphone") || ua.includes("mobile")) {
    return "mobile";
  }
  return "desktop";
}

function detectCountryHint(): string | null {
  if (typeof navigator === "undefined") {
    return null;
  }
  const locale = navigator.language || navigator.languages?.[0] || "";
  const match = locale.match(/[-_](?<country>[A-Za-z]{2})$/);
  const country = match?.groups?.country?.toUpperCase() ?? null;
  return country;
}

export default function AnalyticsTracker() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const hasMounted = useRef(false);

  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    const path = search ? `${pathname}?${search}` : pathname;
    const sessionId = getOrCreateSessionId();
    void recordAnalyticsVisit({
      path,
      referrer: document.referrer || null,
      user_agent: navigator.userAgent,
      device_hint: detectDeviceHint(),
      country_hint: detectCountryHint(),
      page_title: document.title,
      session_id: sessionId,
      event_type: "route_change",
      bot_hint: false,
    }).catch(() => undefined);
  }, [pathname, search]);

  return null;
}
