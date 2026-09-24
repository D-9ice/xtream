import { Suspense, type ReactNode } from "react";
import type { Metadata, Viewport } from "next";

import "./globals.css";
import "./sidebar-branding.css";
import AnalyticsTracker from "./AnalyticsTracker";
import AuthGateGuard from "./AuthGateGuard";
import PwaInstallPrompt from "./PwaInstallPrompt";
import PwaRegister from "./PwaRegister";

const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim();
const vercelProductionUrl = process.env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
const canonicalSiteUrl = configuredSiteUrl || (vercelProductionUrl ? `https://${vercelProductionUrl}` : undefined);

export const metadata: Metadata = {
  ...(canonicalSiteUrl ? { metadataBase: new URL(canonicalSiteUrl) } : {}),
  title: "Pro Creator Pro",
  description: "AI-powered professional content creation platform",
  manifest: "/manifest.webmanifest",
  alternates: {
    canonical: "/",
  },
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/app-icon.png",
  },
  appleWebApp: {
    capable: true,
    title: "Pro Creator Pro",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: "#020b2a",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <PwaRegister />
        <Suspense fallback={null}>
          <AnalyticsTracker />
        </Suspense>
        <PwaInstallPrompt />
        <AuthGateGuard>{children}</AuthGateGuard>
      </body>
    </html>
  );
}
