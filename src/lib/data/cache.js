const DEFAULT_TIMEOUT_MS = 4000;

async function cachedResponse(url) {
  if (!("caches" in globalThis)) return null;
  try {
    return await caches.match(url);
  } catch (_) {
    return null;
  }
}

async function fetchJson(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`${url}: ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

export async function cacheFirst(url, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const cached = await cachedResponse(url);
  if (cached) {
    // The service worker updates its cache when this succeeds. It is deliberately
    // detached from the response path: a stalled network must never hold up data
    // that is already saved on the phone.
    void fetchJson(url, timeoutMs).catch(() => {});
    return cached.json();
  }
  return fetchJson(url, timeoutMs);
}

export async function networkFirst(url, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  try {
    return await fetchJson(url, timeoutMs);
  } catch (error) {
    const cached = await cachedResponse(url);
    if (cached) return cached.json();
    throw error;
  }
}

export function siteUrl(url) {
  return url.startsWith("/") ? url : `/${url}`;
}
