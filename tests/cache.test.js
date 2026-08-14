import assert from "node:assert/strict";
import test from "node:test";

import { cacheFirst } from "../src/lib/data/cache.js";

/* The property is "the saved copy does not wait for the network", and it used to
   be checked by timing the call and asserting under 100 ms. That is a proxy for
   the real thing and a flaky one: it measures how busy the machine is, and it
   failed in a full-suite run while passing every time on its own.

   Asserting it directly instead. The stalled fetch here never settles at all, so
   a `cacheFirst` that awaited it could not return — the test would hang and trip
   its own timeout with a clear message, rather than miss a threshold by 90 ms on
   a loaded runner. */
test("cacheFirst returns saved data without waiting for a stalled network",
  { timeout: 5000 }, async t => {
    const originalCaches = globalThis.caches;
    const originalFetch = globalThis.fetch;
    t.after(() => {
      globalThis.caches = originalCaches;
      globalThis.fetch = originalFetch;
    });

    let refreshStarted = false;
    globalThis.caches = {
      match: async () => new Response(JSON.stringify({ source: "saved" })),
    };
    globalThis.fetch = () => {
      refreshStarted = true;
      return new Promise(() => {});
    };

    assert.deepEqual(
      await cacheFirst("/data/current.json", { timeoutMs: 20 }),
      { source: "saved" },
    );
    // Detached, not skipped. The service worker still refreshes its copy; it
    // just never holds up data already on the phone.
    assert.equal(refreshStarted, true, "the background refresh must still be kicked off");
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
