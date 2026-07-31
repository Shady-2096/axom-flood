/// <reference lib="webworker" />

import { build, files, version } from "$service-worker";

const worker = /** @type {ServiceWorkerGlobalScope} */ (globalThis.self);
const CACHE = `axom-flood-v12-${version}`;
const ROUTES = ["/home/", "/camps/", "/report/", "/emergency/", "/settings/"];
const scopedPath = path => new URL(path, worker.registration.scope).pathname;
const DEV_PATH_PREFIXES = ["/@fs/", "/@id/", "/@vite/", "/.svelte-kit/", "/node_modules/", "/src/"];

// `$service-worker` lists every generated module in `build`, including the map
// and reporting components. Those two components are deliberately lazy, so the
// install step discovers and saves only modules referenced by the prerendered
// route shells. Dynamic chunks are cached later, if and when somebody opens
// them. This is also why `files` is filtered instead of blindly precached: the
// village index is about 9.5 MB and must never be a first-visit download.
const BUILD_PATHS = new Set(build.map(scopedPath));
const ERROR_SHELL = [...BUILD_PATHS].find(path => /\/nodes\/1\.[^/]+\.js$/.test(path));
const STATIC_SHELL = files
  .map(scopedPath)
  .filter(path =>
    !path.startsWith("/data/")
    && !path.startsWith("/tiles/")
    && !path.endsWith(".pmtiles")
    && !path.endsWith(".tif")
    && !path.endsWith(".tiff")
    && path !== "/report.css"
    && path !== "/social-card.jpg"
    && path !== "/assam-river-landscape.avif"
  );
const SHELL_PATHS = new Set([...BUILD_PATHS, ...STATIC_SHELL, "/data/current.json", ...ROUTES]);
const MUTABLE_DATA_PATHS = new Set([
  "/data/current.json",
  "/data/impact-current.json",
  "/data/impact-history.json",
  "/data/impact-status.json",
  "/data/asdma-season-losses.json",
]);

async function fetchFresh(path) {
  return fetch(path, { cache: "reload" });
}

async function cacheRouteShell(cache, route) {
  const response = await fetchFresh(route);
  if (!response.ok) return;
  await cache.put(route, response.clone());
  const html = await response.text();
  const referencedBuildFiles = [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
    .map(match => new URL(match[1], worker.registration.scope).pathname)
    .filter(path => BUILD_PATHS.has(path));
  for (const path of referencedBuildFiles) {
    try {
      const asset = await fetchFresh(path);
      if (asset.ok) await cache.put(path, asset);
    } catch (_) { /* install remains useful with a partial shell */ }
  }
}

worker.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    for (const asset of STATIC_SHELL) {
      try {
        const response = await fetchFresh(asset);
        if (response.ok) await cache.put(asset, response);
      } catch (_) { /* install remains useful with a partial shell */ }
    }
    for (const route of ROUTES) {
      try {
        await cacheRouteShell(cache, route);
      } catch (_) { /* install remains useful with a partial shell */ }
    }
    if (ERROR_SHELL) {
      try {
        const response = await fetchFresh(ERROR_SHELL);
        if (response.ok) await cache.put(ERROR_SHELL, response);
      } catch (_) { /* the normal route shell is still useful */ }
    }
    try {
      const pointerResponse = await fetch("/data/current.json", { cache: "no-store" });
      if (pointerResponse.ok) {
        await cache.put("/data/current.json", pointerResponse.clone());
        const pointer = await pointerResponse.json();
        // Only the alert bundle is precached. The village index is about 9.5 MB:
        // precaching it here made a first visit cost roughly thirty minutes on 2G
        // and that much of the reader's data allowance, before showing a river
        // level. It is cached by the fetch handler if and when a search needs it.
        const contentUrl = new URL(pointer.content_url, worker.registration.scope);
        const contentResponse = await fetch(contentUrl, { cache: "reload" });
        if (contentResponse.ok) await cache.put(contentUrl, contentResponse);
      }
    } catch (_) { /* a prior cache may still be available */ }
    await worker.skipWaiting();
  })());
});

worker.addEventListener("activate", event => event.waitUntil((async () => {
  const cachesToDelete = (await caches.keys()).filter(name =>
    name.startsWith("axom-flood-") && name !== CACHE
  );
  await Promise.all(cachesToDelete.map(name => caches.delete(name)));
  await worker.clients.claim();
})()));

// Data files carrying a content hash in their name are immutable, so a cached
// copy is the right copy and can be served immediately. Mutable pointers,
// indexes, and reviewed checkpoints stay network-first even though only the
// primary data/current.json pointer is precached with the shell.
//
// The application shell does not carry content hashes at its public route URLs:
// serving it from cache first left every returning reader one release behind,
// which is how a fixed search could still come back empty on a phone that had
// opened the site before. The shell asks the network first and falls back to
// cache, so being offline still opens the app while being online means being
// current.
worker.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== worker.location.origin) return;
  // PMTiles and large raster sources rely on HTTP byte ranges. Cache Storage
  // must not turn a 206 response into a poisoned whole-file cache entry, and a
  // first visit must never download an archive in full. Let the browser and
  // range-capable origin handle these requests directly.
  const rangeRequest = event.request.headers.has("range");
  const tileArchive = url.pathname.startsWith("/tiles/")
    || url.pathname.endsWith(".pmtiles")
    || url.pathname.endsWith(".tif")
    || url.pathname.endsWith(".tiff");
  if (rangeRequest || tileArchive) {
    event.respondWith(fetch(event.request));
    return;
  }
  // A previously installed production worker may still control localhost when
  // Vite starts on the same origin. Development modules must always come from
  // Vite; caching them makes hot reload and even a normal refresh serve old
  // component code indefinitely.
  if (DEV_PATH_PREFIXES.some(prefix => url.pathname.startsWith(prefix))) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
    return;
  }
  const isNavigation = event.request.mode === "navigate";
  const isNetworkFirst = isNavigation
    || SHELL_PATHS.has(url.pathname)
    || MUTABLE_DATA_PATHS.has(url.pathname);
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    if (isNetworkFirst) {
      try {
        // "reload" bypasses the browser HTTP cache, which could otherwise hand
        // back the previous release and defeat asking the network first.
        const response = await fetch(event.request, { cache: "reload" });
        if (response.ok) await cache.put(event.request, response.clone());
        return response;
      } catch (_) {
        const cached = await cache.match(event.request, {
          ignoreSearch: isNavigation,
        });
        if (cached) return cached;
        if (isNavigation) {
          return (await cache.match("/home/"))
            || (await cache.match("/"))
            || Response.error();
        }
        return Response.error();
      }
    }
    const cached = await cache.match(event.request);
    if (cached) return cached;
    try {
      const response = await fetch(event.request);
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (_) {
      return isNavigation
        ? (await cache.match("/home/")) || Response.error()
        : Response.error();
    }
  })());
});

worker.addEventListener("push", event => {
  const data = event.data?.json() || {};
  event.waitUntil(worker.registration.showNotification(data.title || "Axom Flood", {
    body: data.body || "A new river update is available.",
    icon: "/icon.svg",
    badge: "/icon.svg",
    tag: data.locality_id || "axom-flood",
    data: { url: data.url || "/home/" },
  }));
});

worker.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(worker.clients.openWindow(event.notification.data.url));
});
