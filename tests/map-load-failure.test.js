/**
 * What the reader gets when the detailed map cannot finish loading.
 *
 * MapLibre fires `load` only once the whole style resolves, and that style
 * reaches two third-party hosts: the OpenStreetMap tile server and the protomaps
 * glyph CDN. Anything that stops one of them -- a captive portal, an ISP filter,
 * a corporate proxy, a link too slow to finish -- means `load` never arrives.
 *
 * Every failure handler used to be registered inside the `load` callback, so
 * none of them was listening for that. `initialize()` could not catch it either:
 * it resolves when the Map is constructed, and the style loads afterwards. The
 * result was "Drawing the Assam atlas…" forever, on a screen where the river
 * reading beside it was perfectly fine. Reproduced in a browser with those two
 * hosts blocked.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const detailedMap = await readFile(
  new URL("../src/lib/components/DetailedRiverMap.svelte", import.meta.url),
  "utf8",
);
const plainMap = await readFile(
  new URL("../src/lib/components/RiverMap.svelte", import.meta.url),
  "utf8",
);

test("a style that never finishes loading gives up instead of spinning", () => {
  assert.match(detailedMap, /const MAP_LOAD_TIMEOUT_MS = 15_000;/);
  assert.match(detailedMap, /loadWatchdog = setTimeout\(\s*\(\) => \{\s*if \(!ready\) mapFailed = true;/);
});

test("the watchdog is armed before load, not inside it", () => {
  // The whole bug was that everything watching for failure was registered in
  // the callback that failure prevents. Arming order is the fix, so assert it.
  const armed = detailedMap.indexOf("loadWatchdog = setTimeout");
  const loadCallback = detailedMap.indexOf('map.once("load"');
  assert.ok(armed > 0 && loadCallback > 0);
  assert.ok(armed < loadCallback, "the watchdog must be armed before map.once('load')");
});

test("a map that does load cancels the watchdog", () => {
  const loadCallback = detailedMap.indexOf('map.once("load"');
  const cleared = detailedMap.indexOf("clearTimeout(loadWatchdog)", loadCallback);
  const readySet = detailedMap.indexOf("ready = true", loadCallback);
  assert.ok(cleared > loadCallback, "load must clear the watchdog");
  assert.ok(cleared < readySet, "clear it before the work, so a slow load cannot race it");
});

test("the watchdog is cleared when the component goes away", () => {
  assert.match(detailedMap, /clearTimeout\(loadWatchdog\);/);
  const clears = detailedMap.match(/clearTimeout\(loadWatchdog\)/g) || [];
  assert.ok(clears.length >= 2, "cleared on load and on teardown");
});

test("the fallback map needs no network at all", () => {
  // `mapFailed` swaps in RiverMap. That is only an improvement on a spinner if
  // RiverMap can draw for a reader who cannot reach a tile server -- which is
  // the exact reader who gets here.
  assert.match(detailedMap, /\{#if mapFailed\}\s*<RiverMap/);
  assert.doesNotMatch(plainMap, /https?:\/\//);
  assert.doesNotMatch(plainMap, /\bfetch\(/);
});

test("the detailed map is the one carrying the third-party hosts", () => {
  // If these ever move into the fallback, the fallback stops being a fallback.
  assert.match(detailedMap, /cdn\.protomaps\.com/);
  assert.match(detailedMap, /tile\.openstreetmap\.org/);
});

test("the loading pill clears the bulletin sheet on a phone", () => {
  // The map is full-bleed and the bulletin floats over its lower half, so a
  // plain `top: 50%` centred "Drawing the Assam atlas…" on top of the card and
  // covered the words "Local flood bulletin". Every other note in this component
  // is already lifted clear of the sheet with --atlas-panel-h; this one was
  // missed. Measured at 375x812: pill 262-291, card starts at 344.
  const phone = detailedMap.slice(detailedMap.indexOf("@media (max-width: 859px)"));
  assert.match(
    phone,
    /\.map-loading \{ top: calc\(\(100dvh - var\(--atlas-panel-h, 240px\)\) \/ 2\); \}/,
  );
});
