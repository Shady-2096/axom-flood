import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const styles = await readFile(new URL("../static/styles.css", import.meta.url), "utf8");
const lightTheme = styles.match(/:root\[data-theme="light"\]\s*\{(?<tokens>[\s\S]*?)\n\}/)?.groups?.tokens;

test("light theme uses authored mineral fields and a deep river frame", () => {
  assert.ok(lightTheme, "light theme token block should exist");
  assert.match(lightTheme, /--ground:\s*#dfeaec;/);
  assert.match(lightTheme, /--surface:\s*#f7faf8;/);
  assert.match(lightTheme, /--chrome:\s*#063947;/);
  assert.match(lightTheme, /--chrome-active:\s*#0b5060;/);
});

test("light mode keeps the restored navigation bar on the river chrome", () => {
  assert.match(
    styles,
    /:root\[data-theme="light"\]\s+\.site-header\s*\{[\s\S]*?background:\s*var\(--chrome\);/
  );
});

/* The calibrated scale moved out of styles.css and into the component that
   computes its marker positions, so these assertions follow it. What they
   protect is unchanged: amber is 2.68:1 as type on paper, so a threshold label
   must never take raw --signal as a foreground. */
const technicalPanel = await readFile(
  new URL("../src/lib/components/TechnicalPanel.svelte", import.meta.url),
  "utf8",
);

test("gauge details lead with the selected area and identify the gauge separately", () => {
  assert.match(technicalPanel, /<p class="data-label">Selected area<\/p>/);
  assert.match(technicalPanel, /<h2>\{locality\?\.revenue_circle[\s\S]*?\{locality\?\.district/);
  assert.match(technicalPanel, /class="gauge-attribution"[\s\S]*?<strong>River reading:<\/strong>/);
  assert.match(technicalPanel, /\{gauge\?\.site_name \? `\$\{gauge\.site_name\} gauge`/);
});

test("threshold marks use the readable foregrounds, never a raw safety field", () => {
  assert.match(technicalPanel, /\.track-mark\.warning b\s*\{\s*color:\s*var\(--signal-ink\);\s*\}/);
  assert.match(technicalPanel, /\.track-mark\.danger b\s*\{\s*color:\s*var\(--danger-text\);\s*\}/);
  assert.doesNotMatch(technicalPanel, /\.track-mark\.warning b\s*\{\s*color:\s*var\(--signal\);/);
});

/* The zone band is the one place a raw safety field is correct, because it is a
   field and not type. It must stay mixed into an opaque surface: mixing toward
   transparent is what made the zones invisible on the night ground. */
test("the zone band mixes safety fields into an opaque surface", () => {
  assert.match(technicalPanel, /color-mix\(in srgb, var\(--signal\) \d+%, var\(--surface\)\)/);
  assert.match(technicalPanel, /color-mix\(in srgb, var\(--danger\) \d+%, var\(--surface\)\)/);
  assert.doesNotMatch(technicalPanel, /color-mix\(in srgb, var\(--(signal|danger)\) \d+%, transparent\)/);
});

/* --danger and --signal are global colour tokens. Reusing those names for the
   band's stop positions shadowed them for the whole subtree and silently
   invalidated the gradient, so the position variables stay namespaced. */
test("scale positions do not shadow global safety colour tokens", () => {
  assert.match(technicalPanel, /--at-warn:/);
  assert.match(technicalPanel, /--at-danger:/);
  assert.doesNotMatch(technicalPanel, /--danger:\$\{/);
  assert.doesNotMatch(technicalPanel, /--warn:\$\{/);
});

const floodBulletin = await readFile(
  new URL("../src/lib/components/FloodBulletin.svelte", import.meta.url),
  "utf8",
);

/* The bulletin's base fields are scoped to its component and load after
   styles.css. Anything that set --field for the atlas from the global sheet
   carried the same specificity and always lost, so the panel silently kept the
   component's own colour no matter what was declared out there. The override
   has to live beside the rule it overrides. */
test("the atlas bulletin's fields are declared in the component, not globally", () => {
  assert.match(floodBulletin, /:global\(\.atlas-panel\)\s+\.bulletin\[data-state="no-data"\]/);
  assert.doesNotMatch(styles, /\.atlas-panel\s+\.bulletin\[data-state=[^\]]+\][^{]*\{[^}]*--field:/);
});

/* Smoke is what keeps the briefing panel off the map. Two properties do that
   work, and neither is "dark" — daylight deliberately runs a lighter smoke than
   night. What must hold is that it stays near-neutral, and that it never drifts
   up into the pale range the OSM sheet uses for landcover and built-up areas.
   The field that disappeared was #e8ebea: almost perfectly neutral, and far too
   light, so it sat exactly on the terrain it was supposed to cover. */
const smokeOf = block => block.match(/--smoke:\s*(#[0-9a-f]{6});/i)?.[1];

test("the bulletin smoke field stays near-neutral in both schemes", () => {
  for (const [scheme, value] of [["night", smokeOf(styles)], ["day", smokeOf(lightTheme)]]) {
    assert.ok(value, `${scheme} smoke should be defined`);
    const [r, g, b] = [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16));
    const max = Math.max(r, g, b);
    assert.ok((max - Math.min(r, g, b)) / max < .45, `${scheme} smoke should stay near-neutral, got ${value}`);
  }
});

test("the daylight smoke stays clear of the map's pale landcover range", () => {
  const value = smokeOf(lightTheme);
  const max = Math.max(...[1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16)));
  assert.ok(max < 215, `day smoke must not drift into pale terrain, got ${value}`);
  assert.ok(max > 120, `day smoke should stay light enough to read as daylight, got ${value}`);
});

test("night smoke is darker than daylight smoke", () => {
  const night = Math.max(...[1, 3, 5].map(i => parseInt(smokeOf(styles).slice(i, i + 2), 16)));
  const day = Math.max(...[1, 3, 5].map(i => parseInt(smokeOf(lightTheme).slice(i, i + 2), 16)));
  assert.ok(night < day, `night smoke (${night}) should be darker than day smoke (${day})`);
});

/* Fallbacks are not optional here: the target device is a low-end Android on a
   bad connection, and a translucent field with no blur behind it is a washed-out
   panel over terrain rather than a readable one. */
test("the glass bulletin falls back to an opaque field without backdrop-filter", () => {
  assert.match(floodBulletin, /@supports not \(.*backdrop-filter.*\)/);
  assert.match(floodBulletin, /@media \(prefers-reduced-transparency: reduce\)/);
});
