import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { loadRainfall, rainfallFor, rainfallVisibility } from "../src/lib/data/rainfall.js";

const AS_OF = "2026-08-06T06:00:00+00:00";
const BUILT = new Date("2026-08-06T20:00:00Z");

function artifact(overrides = {}) {
  return {
    schema_version: 1,
    record: "circle_rainfall_estimates",
    run: "late",
    as_of: AS_OF,
    source: {
      attribution: "NASA GPM IMERG (late run)",
      stale_after_hours: 20,
    },
    shared_text: {
      estimate_note: "This is a satellite estimate, not a rain gauge reading.",
      hedge: "Heavy rain can cause local flooding, but this does not confirm flooding at your location.",
    },
    circles: [
      {
        locality_id: "baksa-barama-pt",
        revenue_circle: "Barama",
        status: "estimate",
        window_hours: 24,
        total_precipitation_mm: 72.4,
        windows: { 1: 4.0, 24: 72.4 },
        headline: "Satellite estimates show about 72 mm of rain over Barama circle in the last 24 hours.",
        stale_headline: "Satellite estimates show about 72 mm of rain over Barama circle in the 24 hours up to 11:30 AM on 6 Aug. Nothing newer has arrived.",
      },
      {
        locality_id: "empty-circle",
        revenue_circle: "Empty",
        status: "unavailable",
        window_hours: null,
        total_precipitation_mm: null,
        windows: {},
        headline: "No satellite rainfall estimate is available for Empty circle.",
        stale_headline: null,
      },
    ],
    ...overrides,
  };
}

function serve(files) {
  globalThis.fetch = async url => {
    const path = String(url);
    if (!(path in files)) return new Response("", { status: 404 });
    return new Response(JSON.stringify(files[path]), { status: 200 });
  };
}

const POINTER = {
  schema_version: 1,
  rainfall_url: "data/rainfall-abc.json",
  revision_id: "abc",
  run: "late",
  as_of: AS_OF,
  generated_at: "2026-08-06T20:00:00+00:00",
};

test("a missing rainfall pointer is an absence, never an error the page must handle", async () => {
  serve({});
  assert.equal(await loadRainfall({ now: BUILT }), null);
});

test("an artifact that disagrees with its pointer about the period is dropped", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact({ as_of: "2026-08-05T06:00:00+00:00" }),
  });
  assert.equal(await loadRainfall({ now: BUILT }), null);
});

test("an estimate older than the longest window it describes is dropped, not relabelled", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const fourDaysLater = new Date("2026-08-10T06:00:00Z");
  assert.equal(await loadRainfall({ now: fourDaysLater }), null);
});

test("a fresh estimate keeps the present-tense wording", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const loaded = await loadRainfall({ now: new Date("2026-08-06T18:00:00Z") });
  const rain = rainfallFor(loaded, "baksa-barama-pt");
  assert.equal(rain.status, "estimate");
  assert.match(rain.headline, /in the last 24 hours/);
  assert.equal(rain.totalMm, 72.4);
});

test("an estimate past its own staleness threshold switches to the dated wording", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  // 30 hours after the period ended: past the run's 20-hour threshold, inside
  // the 72-hour drop.
  const loaded = await loadRainfall({ now: new Date("2026-08-07T12:00:00Z") });
  const rain = rainfallFor(loaded, "baksa-barama-pt");
  assert.equal(rain.status, "stale_estimate");
  assert.match(rain.headline, /Nothing newer has arrived/);
  assert.doesNotMatch(rain.headline, /in the last 24 hours/);
});

test("a circle the pipeline could not compute says so rather than going blank", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const loaded = await loadRainfall({ now: new Date("2026-08-06T18:00:00Z") });
  const rain = rainfallFor(loaded, "empty-circle");
  assert.equal(rain.status, "unavailable");
  assert.equal(rain.totalMm, null);
  assert.match(rain.headline, /No satellite rainfall estimate is available/);
});

test("a circle with no boundary is absent from the layer entirely", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const loaded = await loadRainfall({ now: new Date("2026-08-06T18:00:00Z") });
  assert.equal(rainfallFor(loaded, "some-unreviewed-circle"), null);
});

test("every rainfall number reaches the reader with the estimate note and the hedge", async () => {
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const loaded = await loadRainfall({ now: new Date("2026-08-06T18:00:00Z") });
  const rain = rainfallFor(loaded, "baksa-barama-pt");
  assert.match(rain.estimateNote, /satellite estimate/);
  assert.match(rain.hedge, /does not confirm flooding/);
  assert.match(rain.attribution, /NASA GPM IMERG/);
});

test("the rainfall pointer is fetched network-first by the service worker", async () => {
  const worker = await readFile(
    new URL("../src/service-worker.js", import.meta.url),
    "utf8",
  );
  assert.match(worker, /MUTABLE_DATA_PATHS[\s\S]*?"\/data\/rainfall-current\.json"/);
  // The digest-named artifact must not be precached: it changes name every
  // time it changes content, and the shell has a budget.
  assert.equal(worker.includes("rainfall-abc.json"), false);
});

test("the bulletin never shows a rainfall line it was not given", async () => {
  const bulletin = await readFile(
    new URL("../src/lib/components/FloodBulletin.svelte", import.meta.url),
    "utf8",
  );
  assert.match(bulletin, /rainfall = null,/);
  assert.match(bulletin, /\{#if rainfall\}/);
});

test("the visibility rule is one function, so a check cannot disagree with the page", () => {
  // 20 hours is the stale mark the artifact carries, 72 the drop mark. The
  // publication freshness check asks this the same way `loadRainfall` and
  // `rainfallFor` do, so it can never report a layer as visible while the page
  // is dropping it -- which is the failure it exists to catch.
  assert.equal(rainfallVisibility(3, 20), "current");
  assert.equal(rainfallVisibility(20, 20), "current");
  assert.equal(rainfallVisibility(20.1, 20), "stale");
  assert.equal(rainfallVisibility(72, 20), "stale");
  assert.equal(rainfallVisibility(72.1, 20), "dropped");
  assert.equal(rainfallVisibility(null, 20), "dropped");
  assert.equal(rainfallVisibility(Number.NaN, 20), "dropped");
});

test("an estimate past three days is dropped, not relabelled", async () => {
  // The longest window this data describes is three days, so an older artifact
  // is not late news about now. It is a complete account of a period nobody is
  // asking about. Rainfall sat in exactly this state for four days in Aug 2026.
  serve({
    "/data/rainfall-current.json": POINTER,
    "/data/rainfall-abc.json": artifact(),
  });
  const loaded = await loadRainfall({ now: new Date("2026-08-14T02:00:00Z") });
  assert.equal(loaded, null);
});
