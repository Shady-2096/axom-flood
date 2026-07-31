import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { networkFirst } from "../src/lib/data/cache.js";

const dataIndex = await readFile(
  new URL("../src/lib/data/index.js", import.meta.url),
  "utf8",
);
const layout = await readFile(
  new URL("../src/routes/+layout.svelte", import.meta.url),
  "utf8",
);

test("mutable data returns a fresh network revision even when an old cache exists", async () => {
  const originalFetch = globalThis.fetch;
  const originalCaches = globalThis.caches;
  globalThis.caches = {
    match: async () => new Response('{"revision":"old"}'),
  };
  globalThis.fetch = async () => new Response('{"revision":"new"}', { status: 200 });
  try {
    assert.deepEqual(
      await networkFirst("/data/impact-current.json"),
      { revision: "new" },
    );
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.caches = originalCaches;
  }
});

test("mutable data falls back to the saved revision only when the network fails", async () => {
  const originalFetch = globalThis.fetch;
  const originalCaches = globalThis.caches;
  globalThis.caches = {
    match: async () => new Response('{"revision":"saved"}'),
  };
  globalThis.fetch = async () => {
    throw new TypeError("offline");
  };
  try {
    assert.deepEqual(
      await networkFirst("/data/impact-status.json", { timeoutMs: 25 }),
      { revision: "saved" },
    );
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.caches = originalCaches;
  }
});

test("the main river pointer refreshes instead of returning the installed cache first", () => {
  assert.match(dataIndex, /networkFirst\("\/data\/current\.json"\)/);
  assert.doesNotMatch(dataIndex, /cacheFirst\("\/data\/current\.json"\)/);
  assert.match(layout, /initializeData\(\{ force: true \}\)/);
  assert.match(layout, /serviceWorker\?\.(?:addEventListener)|serviceWorker\?\.addEventListener/);
  assert.match(layout, /"controllerchange"/);
});
