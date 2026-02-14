import type { ReactNode } from "react";
import type { Metadata, Viewport } from "next";

import "./globals.css";
import PwaRegister from "./PwaRegister";

export const metadata: Metadata = {
  title: "Pro Creator",
  description: "AI-powered content creation platform",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Pro Creator",
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
        {children}
      </body>
    </html>
  );
}
