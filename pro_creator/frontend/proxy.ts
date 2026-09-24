import type { NextFetchEvent, NextRequest } from "next/server";
import { NextResponse } from "next/server";

const TRACKED_PATH_EXCLUDES = [
  "/api",
  "/_next/static",
  "/_next/image",
  "/favicon.ico",
  "/favicon.ico.png",
  "/manifest.webmanifest",
  "/robots.txt",
  "/sitemap.xml",
  "/app-icon.png",
];

const BOT_MARKERS = [
  "googlebot",
  "bingbot",
  "duckduckbot",
  "slurp",
  "crawler",
  "spider",
  "bot",
  "headless",
  "playwright",
  "puppeteer",
  "selenium",
  "scrapy",
  "curl",
  "wget",
  "python-requests",
  "httpclient",
  "lighthouse",
  "postman",
];

function shouldTrack(request: NextRequest): boolean {
  if (request.method !== "GET") {
    return false;
  }
  const accept = request.headers.get("accept") ?? "";
  if (!accept.includes("text/html")) {
    return false;
  }
  return !TRACKED_PATH_EXCLUDES.some((prefix) => request.nextUrl.pathname.startsWith(prefix));
}

function detectBot(userAgent: string | null): boolean {
  const normalized = (userAgent ?? "").toLowerCase();
  return BOT_MARKERS.some((marker) => normalized.includes(marker));
}

function detectDeviceHint(userAgent: string | null): string {
  const normalized = (userAgent ?? "").toLowerCase();
  if (normalized.includes("ipad") || normalized.includes("tablet") || normalized.includes("kindle") || normalized.includes("silk")) {
    return "tablet";
  }
  if (normalized.includes("android") || normalized.includes("iphone") || normalized.includes("mobile") || normalized.includes("mobi")) {
    return "mobile";
  }
  return "desktop";
}

function detectCountryHint(request: NextRequest): string | null {
  const headers = [
    request.headers.get("cf-ipcountry"),
    request.headers.get("x-vercel-ip-country"),
    request.headers.get("x-country-code"),
    request.headers.get("x-geo-country"),
    request.headers.get("x-country"),
  ];
  for (const header of headers) {
    const normalized = (header ?? "").trim().toUpperCase();
    if (normalized && normalized !== "XX" && normalized !== "UNKNOWN" && normalized !== "N/A") {
      return normalized.slice(0, 2);
    }
  }
  const acceptLanguage = request.headers.get("accept-language") ?? "";
  const localeMatch = acceptLanguage.match(/[-_](?<country>[A-Za-z]{2})/);
  return localeMatch?.groups?.country?.toUpperCase() ?? null;
}

export async function proxy(request: NextRequest, event: NextFetchEvent) {
  const response = NextResponse.next();
  if (!shouldTrack(request)) {
    return response;
  }

  const tenantId = request.headers.get("X-Tenant-ID") ?? "default";
  const userAgent = request.headers.get("user-agent");
  const sessionCookie = request.cookies.get("pc_visit_session")?.value;
  const sessionId =
    sessionCookie ?? globalThis.crypto?.randomUUID?.() ?? `visit-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  if (!sessionCookie) {
    response.cookies.set("pc_visit_session", sessionId, {
      path: "/",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 365,
    });
  }

  const backendBase = process.env.ANALYTICS_BACKEND_URL ?? "http://127.0.0.1:8000";
  const endpoint = new URL("/analytics/visits", backendBase);
  const path = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  event.waitUntil(
    fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-ID": tenantId,
      },
      body: JSON.stringify({
        path,
        referrer: request.headers.get("referer"),
        user_agent: userAgent,
        device_hint: detectDeviceHint(userAgent),
        country_hint: detectCountryHint(request),
        session_id: sessionId,
        event_type: "page_view",
        bot_hint: detectBot(userAgent),
      }),
    }).catch(() => undefined)
  );

  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|favicon.ico.png|manifest.webmanifest|robots.txt|sitemap.xml|app-icon.png).*)"],
};
