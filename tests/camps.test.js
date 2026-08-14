import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  campPhoneNumbers,
  campsForLocality,
  campsSavedLabel,
  normalizeCircleName,
} from "../src/lib/data/camps.js";

const pointer = JSON.parse(await readFile(new URL("../static/data/current.json", import.meta.url)));
const bundle = JSON.parse(await readFile(new URL(`../static/${pointer.content_url}`, import.meta.url)));

test("Census part suffix does not hide Sidli camp records", () => {
  const locality = bundle.localities.find(item => item.locality_id === "chirang-sidli-pt");
  const matches = campsForLocality(bundle.camps, locality);
  assert.equal(normalizeCircleName(locality.revenue_circle), "sidli");
  assert.equal(matches.length, 23);
});

test("duplicate camp rows are rendered once", () => {
  const locality = bundle.localities.find(item => item.locality_id === "chirang-bengtol");
  assert.equal(campsForLocality(bundle.camps, locality).length, 12);
});

test("multiple published camp contacts become separate dial targets", () => {
  assert.deepEqual(campPhoneNumbers("9401736970/ 8638089879"), [
    { display: "9401736970", dial: "9401736970" },
    { display: "8638089879", dial: "8638089879" },
  ]);
});

test("the camps screen dates the camp list, not the river gauge", async () => {
  // It used to render <AgeBlock gauge={context.gauge} />, so a list read from
  // district documents saved eighteen days earlier was headed "3.2 hours old".
  // Every word true about the gauge, none of it true about a single camp under
  // it, on the one screen somebody might act on by travelling.
  const page = await readFile(
    new URL("../src/routes/camps/+page.svelte", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(page, /<AgeBlock/);
  assert.match(page, /campsSavedLabel\(\$dataState\.bundle\.camps_saved_at\)/);
});

test("the bundle carries when the camp listings were saved", () => {
  assert.ok(bundle.camps_saved_at, "camps_saved_at must be published");
  assert.ok(!Number.isNaN(Date.parse(bundle.camps_saved_at)));
});

test("a saved camp list is described as saved, never published or updated", () => {
  // Our fetch time, not the district's. Most notifications are PDFs carrying no
  // date we can parse, and calling a fetch time a publication time would be the
  // same mistake in a new place.
  const now = new Date("2026-08-14T12:00:00+05:30");
  assert.equal(campsSavedLabel("2026-08-14T09:00:00+05:30", now).text, "Saved today");
  assert.equal(campsSavedLabel("2026-08-13T09:00:00+05:30", now).text, "Saved yesterday, 13 Aug");
  assert.equal(campsSavedLabel("2026-07-28T01:54:00+05:30", now).text, "Saved 28 Jul, 17 days ago");
  for (const value of ["2026-08-14T09:00:00+05:30", "2026-07-28T01:54:00+05:30"]) {
    assert.doesNotMatch(campsSavedLabel(value, now).text, /published|updated/i);
  }
});

test("a camp list older than the report window is marked stale", () => {
  const now = new Date("2026-08-14T12:00:00+05:30");
  assert.equal(campsSavedLabel("2026-08-11T09:00:00+05:30", now).stale, false);
  assert.equal(campsSavedLabel("2026-08-10T09:00:00+05:30", now).stale, true);
  assert.equal(campsSavedLabel(null, now), null);
  assert.equal(campsSavedLabel("not a date", now), null);
});
