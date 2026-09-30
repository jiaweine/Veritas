const CACHE = "veritas-shell-v21";
const SHELL = [
  "/",
  "/static/styles.css",
  "/static/audit-harness.css",
  "/static/audit-harness-product.css",
  "/static/audit-notes.css",
  "/static/reproduction.css",
  "/static/runs.css",
  "/static/settings.css",
  "/static/benchmarks.css",
  "/static/reference-workbench.css",
  "/static/reference-surfaces.css",
  "/static/claim-graph.css",
  "/static/finding-navigation.css",
  "/static/mobile-polish.css",
  "/static/app.js",
  "/static/audit-harness.js",
  "/static/audit-harness-product.js",
  "/static/audit-notes.js",
  "/static/reproduction.js",
  "/static/runs.js",
  "/static/settings.js",
  "/static/benchmarks.js",
  "/static/reference-workbench.js",
  "/static/reference-evidence-preview.js",
  "/static/claim-graph.js",
  "/static/finding-navigation.js",
  "/static/icon.svg",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname.includes("/paper")) return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
      if (response.ok && url.origin === self.location.origin) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      }
      return response;
    }))
  );
});