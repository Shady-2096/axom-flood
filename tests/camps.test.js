import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  campPhoneNumbers,
  campsForLocality,
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
