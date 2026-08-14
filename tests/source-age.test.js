/**
 * An age label is a claim about the data underneath it.
 *
 * `AgeBlock` takes a gauge and prints how long ago it reported, which is right
 * on the river bulletin and nowhere else. Two other screens used it anyway,
 * because it was the timestamp in reach:
 *
 *   - Relief camps: "3.2 hours old" over listings read from district documents
 *     saved eighteen days earlier. The one screen somebody might act on by
 *     getting in a boat, and the page's own copy says camp lists change quickly.
 *   - Emergency: "3.3 hours old" over 1070, a hand-maintained constant. A
 *     freshness claim about a number nobody had looked at since July.
 *
 * Every word of both was true about the gauge. Borrowing an age is the same
 * class of mistake as interpolating a reading, so these tests hold each screen
 * to its own source.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { sourceAgeLabel } from "../src/lib/data/age.js";

const NOW = new Date("2026-08-14T12:00:00+05:30");
const pointer = JSON.parse(await readFile(new URL("../static/data/current.json", import.meta.url)));
const bundle = JSON.parse(await readFile(new URL(`../static/${pointer.content_url}`, import.meta.url)));

async function page(name) {
  return readFile(new URL(`../src/routes/${name}/+page.svelte`, import.meta.url), "utf8");
}

test("the verb says what actually happened to the data", () => {
  // "Saved" is when we fetched it. "Checked" is when a person last looked.
  // Neither is "published", which is the source's act and not ours to claim.
  assert.equal(
    sourceAgeLabel("2026-07-28T01:54:00+05:30", { verb: "Saved", staleAfterDays: 3, now: NOW }).text,
    "Saved 28 Jul, 17 days ago",
  );
  assert.equal(
    sourceAgeLabel("2026-07-27T00:00:00+05:30", { verb: "Checked", staleAfterDays: 180, now: NOW })
      .text,
    "Checked 27 Jul, 18 days ago",
  );
});

test("today and yesterday are said the way a person would say them", () => {
  const options = { verb: "Saved", staleAfterDays: 3, now: NOW };
  assert.equal(sourceAgeLabel("2026-08-14T09:00:00+05:30", options).text, "Saved today");
  assert.equal(sourceAgeLabel("2026-08-13T09:00:00+05:30", options).text, "Saved yesterday, 13 Aug");
});

test("staleness is per source, not one number for the whole site", () => {
  // A camp list goes stale in days. 1070 has been ASDMA's number for years, and
  // warning about it weekly would be crying wolf on the screen that can least
  // afford it.
  const camps = { verb: "Saved", staleAfterDays: 3, now: NOW };
  const helplines = { verb: "Checked", staleAfterDays: 180, now: NOW };
  assert.equal(sourceAgeLabel("2026-08-10T09:00:00+05:30", camps).stale, true);
  assert.equal(sourceAgeLabel("2026-08-10T09:00:00+05:30", helplines).stale, false);
  assert.equal(sourceAgeLabel("2026-01-01T09:00:00+05:30", helplines).stale, true);
});

test("a date that cannot be read is null, never a guess", () => {
  const options = { verb: "Saved", staleAfterDays: 3, now: NOW };
  assert.equal(sourceAgeLabel(null, options), null);
  assert.equal(sourceAgeLabel(undefined, options), null);
  assert.equal(sourceAgeLabel("", options), null);
  assert.equal(sourceAgeLabel("not a date", options), null);
});

test("no screen outside the river bulletin dates itself by the gauge", async () => {
  for (const name of ["camps", "emergency"]) {
    assert.doesNotMatch(await page(name), /<AgeBlock/, `${name} must not borrow the gauge's age`);
  }
  const bulletin = await readFile(
    new URL("../src/lib/components/FloodBulletin.svelte", import.meta.url),
    "utf8",
  );
  assert.match(bulletin, /<AgeBlock/, "the river bulletin is where a gauge age belongs");
});

test("the bundle carries a date for every screen that shows one", () => {
  assert.ok(bundle.camps_saved_at, "camps_saved_at must be published");
  assert.ok(bundle.helplines_updated_at, "helplines_updated_at must be published");
  for (const value of [bundle.camps_saved_at, bundle.helplines_updated_at]) {
    assert.ok(!Number.isNaN(Date.parse(value)));
  }
});
