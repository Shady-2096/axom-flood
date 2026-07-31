import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const detailedMap = await readFile(
  new URL("../src/lib/components/DetailedRiverMap.svelte", import.meta.url),
  "utf8",
);

test("MapLibre owns native wheel and pinch gesture handling", () => {
  assert.match(detailedMap, /new maplibre\.Map/);
  assert.match(detailedMap, /cooperativeGestures:\s*false/);
  assert.doesNotMatch(detailedMap, /wheelDebounceTime|gestureZoomDelta|SmoothWheelZoom/);
});

test("wheel and pinch zoom remain continuous", () => {
  assert.match(detailedMap, /map\.scrollZoom\.setWheelZoomRate\(1 \/ 280\)/);
  assert.match(detailedMap, /map\.scrollZoom\.setZoomRate\(1 \/ 60\)/);
  assert.doesNotMatch(detailedMap, /zoomSnap/);
});

test("the atlas remains bounded to the operational Assam area", () => {
  assert.match(detailedMap, /map\.setMaxBounds/);
  assert.match(detailedMap, /minZoom:\s*6/);
  assert.match(detailedMap, /maxZoom:\s*18/);
});
