import type { ReactNode } from "react";
import type { Metadata, Viewport } from "next";

import "./globals.css";
import AnalyticsTracker from "./AnalyticsTracker";
import PwaInstallPrompt from "./PwaInstallPrompt";
import PwaRegister from "./PwaRegister";

export const metadata: Metadata = {
  title: "X'tream",
  description: "AI-powered content creation platform",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/app-icon.png",
  },
  appleWebApp: {
    capable: true,
    title: "X'tream",
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
        <AnalyticsTracker />
        <PwaInstallPrompt />
        {children}
      </body>
    </html>
  );
}
