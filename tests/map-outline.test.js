import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { dissolveRings, signedRingArea, windRing } from "../src/lib/map/outline.js";

const shapes = JSON.parse(
  await readFile(new URL("../config/assam-circle-shapes.json", import.meta.url), "utf8"),
);
const allRings = shapes.circles.flatMap(circle => circle.rings);

// Proper crossings only: rings are built out of segments that share endpoints,
// and touching end-on is not what breaks the triangulation.
function turn(origin, from, to) {
  return (from[0] - origin[0]) * (to[1] - origin[1]) - (from[1] - origin[1]) * (to[0] - origin[0]);
}

function segmentsCross(a1, a2, b1, b2) {
  const d1 = turn(b1, b2, a1);
  const d2 = turn(b1, b2, a2);
  const d3 = turn(a1, a2, b1);
  const d4 = turn(a1, a2, b2);
  if (d1 === 0 || d2 === 0 || d3 === 0 || d4 === 0) return false;
  return (d1 > 0) !== (d2 > 0) && (d3 > 0) !== (d4 > 0);
}

const detailedMap = await readFile(
  new URL("../src/lib/components/DetailedRiverMap.svelte", import.meta.url),
  "utf8",
);

test("the source circle rings are wound both ways", () => {
  // The reason the mask needs normalising at all. If the upstream shapes ever
  // become consistently wound this stops being load-bearing, but the dissolve
  // must keep working either way.
  const positive = allRings.filter(ring => signedRingArea(windRing(ring, true)) > 0);
  assert.equal(positive.length, allRings.length);
  const raw = allRings.filter(ring => signedRingArea(ring) > 0);
  assert.ok(raw.length > 0 && raw.length < allRings.length);
});

test("the circles dissolve to a single Assam outline", () => {
  // earcut only triangulates disjoint holes, so the mask must never be handed
  // the touching per-circle rings: one ring in, one ring out.
  const outline = dissolveRings(allRings);
  assert.equal(outline.length, 1);
  assert.ok(outline[0].length > 1000, `outline had only ${outline[0].length} vertices`);
});

test("the dissolved outline covers the area the circles covered", () => {
  const outline = dissolveRings(allRings);
  const dissolved = Math.abs(signedRingArea(outline[0]));
  const summed = allRings.reduce((total, ring) => total + Math.abs(signedRingArea(ring)), 0);
  // Circles tile the state without overlapping, so their areas should add up to
  // the outline. A dissolve that dropped or duplicated a region fails here.
  assert.ok(
    Math.abs(dissolved - summed) / summed < 0.01,
    `dissolved ${dissolved} vs summed ${summed}`,
  );
});

test("the outline is a simple ring", () => {
  // What the mask actually needs. earcut is defined for simple rings only, and
  // MapLibre re-triangulates the mask for every tile, so a ring that touched or
  // crossed itself had the outside dim painted twice over a wedge of the map —
  // a dark diagonal band that moved and changed shape with the view. Assam's
  // borders follow river channels, so both faults come from the source: two
  // neighbours simplified apart leave their shared seam as a zigzag.
  for (const ring of dissolveRings(allRings)) {
    const points = ring.slice(0, -1);
    const seen = new Set(points.map(point => `${point[0]},${point[1]}`));
    assert.equal(seen.size, points.length, "the outline visits a point twice");

    for (let left = 0; left < points.length; left++) {
      for (let right = left + 2; right < points.length; right++) {
        if (left === 0 && right === points.length - 1) continue;
        assert.ok(
          !segmentsCross(
            points[left], points[(left + 1) % points.length],
            points[right], points[(right + 1) % points.length],
          ),
          `segments ${left} and ${right} cross at ${JSON.stringify(points[left])}`,
        );
      }
    }
  }
});

test("outline rings close and holes wind against the outer ring", () => {
  const outline = dissolveRings(allRings);
  for (const ring of outline) {
    assert.deepEqual(ring[0], ring[ring.length - 1]);
  }
  const outer = windRing([[-180, -85], [180, -85], [180, 85], [-180, 85]], true);
  const hole = windRing(outline[0], false);
  assert.ok(signedRingArea(outer) > 0);
  assert.ok(signedRingArea(hole) < 0);
});

test("the atlas masks with the dissolved outline, not the raw circles", () => {
  assert.match(detailedMap, /dissolveRings\(shapesDocument\.circles\.flatMap/);
  assert.match(detailedMap, /windRing\(\[\[-180, -85\]/);
});

test("circle picking reads the id off the feature properties", () => {
  // A GeoJSON source only keeps feature ids that are non-negative integers, so
  // the "circle-N" ids never survive into the tile and event.features[0].id is
  // not the circle. Reading feature.id here silently broke every click.
  const handlers = detailedMap.match(/map\.on\("(?:click|mousemove)", "circle-fill"[\s\S]*?\}\);/g);
  assert.equal(handlers?.length, 2);
  for (const handler of handlers) {
    assert.match(handler, /properties\?\.featureId/);
    assert.doesNotMatch(handler, /features\?\.\[0\]\?\.id/);
  }
});

test("the map is drawn the same way under both themes", () => {
  // Only the interface around the map follows the theme, in CSS. Nothing in
  // here may branch on it: a basemap that darkened with the theme fought the
  // dimmed surround, and the earlier theme pass was skipped on first paint
  // anyway, so light mode kept dark map colours until the theme was toggled.
  // Scoped to the script: the stylesheet still themes the controls drawn over
  // the map, which is interface and should follow the theme.
  const script = detailedMap.slice(0, detailedMap.indexOf("</script>"));
  const code = script.replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(code, /isDarkTheme|applyTheme|data-theme/);
  assert.doesNotMatch(code, /setPaintProperty\([^)]*dark/);
});
