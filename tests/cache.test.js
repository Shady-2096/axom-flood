import assert from "node:assert/strict";
import test from "node:test";

import { cacheFirst } from "../src/lib/data/cache.js";

test("cacheFirst returns saved data without waiting for a stalled network", async t => {
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  });

  globalThis.caches = {
    match: async () => new Response(JSON.stringify({ source: "saved" })),
  };
  globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });

  const start = performance.now();
  const value = await cacheFirst("/data/current.json", { timeoutMs: 20 });
  assert.deepEqual(value, { source: "saved" });
  assert.ok(performance.now() - start < 100);
});

test("cacheFirst fetches with a timeout when no saved response exists", async t => {
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  });

  globalThis.caches = { match: async () => null };
  globalThis.fetch = async () => new Response(JSON.stringify({ source: "network" }));
  assert.deepEqual(
    await cacheFirst("/data/current.json", { timeoutMs: 20 }),
    { source: "network" },
  );
});
