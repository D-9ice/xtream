"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

const SUPPORTED = new Set(["youtube", "facebook", "instagram", "x", "tiktok"]);

export default function SocialOAuthCallbackPage() {
  const router = useRouter();
  const params = useParams<{ platform: string }>();
  const searchParams = useSearchParams();

  useEffect(() => {
    const platform = String(params?.platform ?? "").toLowerCase();
    if (!SUPPORTED.has(platform)) {
      router.replace("/?nav=publish&social_oauth_error=unsupported_platform");
      return;
    }

    const next = new URLSearchParams(searchParams.toString());
    next.set("nav", "publish");
    next.set("social_oauth", platform);
    router.replace(`/?${next.toString()}`);
  }, [params, router, searchParams]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-midnight px-6 text-sm text-slate-300">
      Completing social account authorization...
    </main>
  );
}
