// Keep this conservative: caching dev bundles (/_next/*) will break Next.js development.
// Bump this whenever core PWA branding assets change so installed clients drop stale legacy-brand assets.
const CACHE_NAME = "procreator-pro-v5";
const PRECACHE_URLS = [
  "/",
  "/manifest.webmanifest",
  "/app-icon.png",
  "/favicon.ico",
  "/procreator-pro-logo.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  // Never cache Next internals.
  if (url.pathname.startsWith("/_next/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/"))
    );
    return;
  }

  // Only cache a small precache set; fetch everything else directly.
  if (!PRECACHE_URLS.includes(url.pathname)) {
    return;
  }

  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});
