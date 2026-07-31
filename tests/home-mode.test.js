import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(
  new URL("../src/routes/+page.svelte", import.meta.url),
  "utf8",
);
const appShell = await readFile(
  new URL("../src/app.html", import.meta.url),
  "utf8",
);
const loadingState = await readFile(
  new URL("../src/lib/components/LoadingState.svelte", import.meta.url),
  "utf8",
);
const detailedMap = await readFile(
  new URL("../src/lib/components/DetailedRiverMap.svelte", import.meta.url),
  "utf8",
);
const fallbackMap = await readFile(
  new URL("../src/lib/components/RiverMap.svelte", import.meta.url),
  "utf8",
);
const gaugeSymbol = await readFile(
  new URL("../src/lib/map/gaugeSymbol.js", import.meta.url),
  "utf8",
);
const provenanceNotes = await readFile(
  new URL("../src/lib/components/ProvenanceNotes.svelte", import.meta.url),
  "utf8",
);
const styles = await readFile(
  new URL("../static/styles.css", import.meta.url),
  "utf8",
);
const floodBulletin = await readFile(
  new URL("../src/lib/components/FloodBulletin.svelte", import.meta.url),
  "utf8",
);
const situation = await readFile(
  new URL("../src/routes/situation/+page.svelte", import.meta.url),
  "utf8",
);

test("home resolves the client render mode before cached locality data paints", () => {
  assert.match(
    home,
    /onMount\(\(\) => \{[\s\S]*?resolveMode\(\);\s*\}\);/,
  );
  assert.doesNotMatch(
    home,
    /\$effect\(\(\) => \{[\s\S]*?resolveMode\(\);/,
  );
});

test("manual full-mode loading degrades to the document layout on failure", () => {
  assert.match(
    home,
    /async function switchToFullMode\(\)[\s\S]*?try \{[\s\S]*?await loadFullMode\(\);[\s\S]*?\} catch \{[\s\S]*?renderMode = "light";[\s\S]*?offerFullMode = false;/,
  );
});

test("an explicit impact-layer link opens the atlas without persisting a display choice", () => {
  assert.match(home, /const requestedLayer = new URL\(window\.location\.href\)\.searchParams\.get\("layer"\)/);
  assert.match(home, /if \(requestedLayer\) \{[\s\S]*?applyMode\("full"\);[\s\S]*?loadFullMode\(\)/);
  assert.doesNotMatch(
    home.match(/if \(requestedLayer\) \{(?<body>[\s\S]*?)\n\s*\}/)?.groups?.body || "",
    /selectRenderMode/,
  );
});

test("ASDMA impact uses the main atlas and the situation page has no second map", () => {
  assert.match(detailedMap, /loadImpactOverlay/);
  assert.match(detailedMap, /Map view/);
  assert.match(detailedMap, /class="drawer-key"/);
  assert.match(detailedMap, /\{@render mapKey\(\)\}/);
  assert.doesNotMatch(detailedMap, /class="legend-toggle"/);
  // The key stands on the right and stays there. A map whose symbols have to be
  // remembered between visits is a map people read wrong, and the moment that
  // matters most is the one where somebody is reading it in a hurry.
  assert.match(detailedMap, /class="map-legend"/);
  assert.match(detailedMap, /class:river-key=\{!isImpactLayer\(\)\}/);
  assert.doesNotMatch(detailedMap, /attached-key|showAttachedKey/);
  assert.match(detailedMap, /Affected people/);
  assert.match(detailedMap, /Affected villages/);
  assert.doesNotMatch(detailedMap, /Latest official gauge status/);
  assert.doesNotMatch(detailedMap, /People reported by revenue circle/);
  assert.doesNotMatch(detailedMap, /Villages reported by revenue circle/);
  assert.match(detailedMap, /class="layer-trigger"/);
  assert.match(detailedMap, /class="drawer-tools"/);
  assert.match(home, /onlayerchange=\{handleMapLayerChange\}/);
  assert.match(home, /onmoreinfo=\{showTechnicalDetails\}/);
  assert.doesNotMatch(home, /class="atlas-more"/);
  assert.doesNotMatch(floodBulletin, /Official CWC source/);
  assert.match(
    home,
    /if \(globalThis\.matchMedia\?\.\("\(max-width: 859px\), \(max-height: 820px\)"\)\?\.matches\) \{\s*panelCollapsed = true;/,
  );
  assert.match(situation, /href="\/\?layer=affected_population"/);
  assert.doesNotMatch(situation, /ImpactMap|MapComponent|openMap|showMap/);
});

test("river severity never fills a revenue circle, and never scales a symbol by area", () => {
  // Two rules, and the second one is newer. Colouring a whole circle from one
  // point reading was wrong because a gauge does not describe a circle. Growing
  // a halo from 11px to 36px was wrong for the same reason one level down: on a
  // map, a bigger circle means a bigger area, and that area meant nothing.
  assert.doesNotMatch(detailedMap, /entry\.area\.state === "warning"/);
  assert.doesNotMatch(detailedMap, /state-\$\{area\.state\}/);
  assert.doesNotMatch(fallbackMap, /\.area\[data-state="warning"\]/);
  assert.doesNotMatch(detailedMap, /outerRadius|innerRadius|gaugeHalo/);
  assert.doesNotMatch(fallbackMap, /gauge-halo/);

  // One size, one ring radius, severity in the fill and the glyph.
  assert.match(gaugeSymbol, /export const GAUGE_RING_RADIUS = \d+/);
  assert.match(gaugeSymbol, /export const GAUGE_SIZE = \d+/);
  assert.match(detailedMap, /"--gauge-size", `\$\{GAUGE_SIZE\}px`/);
  assert.match(detailedMap, /"--gauge-ring-size", `\$\{GAUGE_RING_RADIUS \* 2\}px`/);
  assert.match(fallbackMap, /class="gauge-ring"/);
  assert.match(fallbackMap, /class="gauge-symbol"/);

  // Every state has a glyph, so colour is never the only carrier.
  for (const state of ["normal", "warning", "danger", "extreme"]) {
    assert.match(gaugeSymbol, new RegExp(`${state}:\\s*'<path`));
  }

  // The ramp comes from tokens that respond to the theme, not from the four raw
  // literals the maps used to carry — one of which was a danger colour lighter
  // than the warning it escalates from.
  assert.doesNotMatch(detailedMap, /#74c4d6|#e8792e|#f08a6b|#d6452b/);
  assert.doesNotMatch(fallbackMap, /var\(--danger-text\)/);
  assert.match(styles, /--gauge-warning:/);
  assert.match(styles, /--gauge-danger:/);
  assert.match(styles, /--gauge-extreme:/);

  // The most severe state the system reports gets its own row and its own name.
  assert.match(gaugeSymbol, /Above the highest recorded flood/);
});

test("the selected circle is tied to the gauge its reading comes from", () => {
  // Silonijan showed "Below warning level" off a gauge 101 km away in another
  // basin while a warning-level gauge sat nearer on the same screen, and nothing
  // on the map connected the reading to its instrument.
  assert.match(detailedMap, /function gaugeLinkData/);
  assert.match(detailedMap, /id: "gauge-link-line"/);
  assert.match(detailedMap, /mapping\.far \|\| mapping\.much_nearer_gauge_exists/);
  assert.match(detailedMap, /km to \$\{gauge\.site_name/);
  assert.match(provenanceNotes, /much_nearer_gauge_exists/);
  assert.match(provenanceNotes, /distance_km/);

  // Two strokes, so a line crossing the whole state stays legible over pale
  // farmland and dark hill shading alike.
  assert.match(detailedMap, /id: "gauge-link-casing"/);

  // The distance shows on every selection, not only the flagged ones. Somebody
  // who only ever sees the label on bad mappings has nothing to compare it with,
  // so the number itself stops carrying information.
  const link = detailedMap.match(/function gaugeLinkData[\s\S]*?\n  \}\n/)[0];
  assert.match(link, /Number\.isFinite\(mapping\.distance_km\)/);
  assert.doesNotMatch(link, /if \(!flagged/);
});

test("the removed post-render layout helper leaves no dead tick import", () => {
  assert.doesNotMatch(home, /import\s*\{[^}]*\btick\b[^}]*\}\s*from "svelte"/);
});

test("returning full-mode visits reserve the atlas plane before data restores", () => {
  assert.match(appShell, /localStorage\.getItem\("locality"\)/);
  assert.match(appShell, /dataset\.returningView\s*=/);
  assert.match(home, /<LoadingState home \/>/);
  assert.match(
    loadingState,
    /html\[data-returning-view="atlas"\][\s\S]*?\.home-loading[\s\S]*?background:\s*var\(--ground-deep\)/,
  );
});

test("the detailed map waits for its first basemap result before fading in", () => {
  assert.match(detailedMap, /let visualReady = \$state\(false\)/);
  assert.match(detailedMap, /map\.once\("idle", revealMap\)/);
  assert.match(detailedMap, /revealTimer = setTimeout\(revealMap, 2500\)/);
  assert.match(detailedMap, /if \(sourceId === "streets" \|\| sourceId === "satellite"\) tilesFailed = true/);
  assert.match(detailedMap, /\.detailed-map\.visual-ready\s*\{\s*opacity:\s*1;\s*\}/);
  assert.match(detailedMap, /@media \(prefers-reduced-motion: reduce\)/);
});

test("trackpad and pinch zoom stay continuous instead of snapping", () => {
  assert.match(detailedMap, /new maplibre\.Map/);
  assert.match(detailedMap, /map\.scrollZoom\.setWheelZoomRate\(1 \/ 280\)/);
  assert.match(detailedMap, /map\.scrollZoom\.setZoomRate\(1 \/ 60\)/);
  assert.doesNotMatch(detailedMap, /zoomSnap|SmoothWheelZoom/);
});

test("the full atlas opens technical details from the bulletin instead of a floating button", () => {
  assert.doesNotMatch(home, /class="atlas-more"/);
  assert.match(home, /onmoreinfo=\{showTechnicalDetails\}/);
  assert.match(floodBulletin, /label: "More info"/);
  assert.match(floodBulletin, /aria-controls="technical-details"/);
  assert.match(home, /technicalOpen = true/);
  assert.match(home, /technicalSection\?\.scrollIntoView/);
  assert.match(home, /bind:open=\{technicalOpen\}/);
});
