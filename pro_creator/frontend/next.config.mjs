import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isDevelopment = process.env.NODE_ENV !== "production";
const backendOrigin = (
  process.env.PRO_CREATOR_BACKEND_ORIGIN ??
  (isDevelopment ? "http://127.0.0.1:8000" : "")
).replace(/\/$/, "");
const assetOrigin = (process.env.NEXT_PUBLIC_ASSET_ORIGIN ?? "").replace(/\/$/, "");

const connectSources = ["'self'", "ws:", "wss:"];
if (backendOrigin) connectSources.push(backendOrigin);

const imageSources = ["'self'", "data:", "blob:"];
const mediaSources = ["'self'", "blob:"];
if (assetOrigin) {
  imageSources.push(assetOrigin);
  mediaSources.push(assetOrigin);
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: __dirname,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "base-uri 'self'",
              "form-action 'self'",
              "frame-ancestors 'none'",
              "object-src 'none'",
              `img-src ${imageSources.join(" ")}`,
              "font-src 'self' data:",
              "style-src 'self' 'unsafe-inline'",
              `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
              `connect-src ${connectSources.join(" ")}`,
              `media-src ${mediaSources.join(" ")}`,
            ].join("; "),
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Resource-Policy", value: "same-site" },
        ],
      },
    ];
  },
  async rewrites() {
    if (!backendOrigin) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
