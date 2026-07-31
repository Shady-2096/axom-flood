import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  configureSearch,
  matchRank,
  nearbyMatches,
  searchKeys,
} from "../src/lib/data/search.js";

const pointer = JSON.parse(await readFile(new URL("../static/data/current.json", import.meta.url)));
const bundle = JSON.parse(await readFile(new URL(`../static/${pointer.content_url}`, import.meta.url)));
configureSearch(bundle, pointer);

test("consonant-skeleton matching preserves the Sibsagar spelling variant", () => {
  assert.notEqual(matchRank(searchKeys("Sivasagar"), searchKeys("sibsagar")), null);
});

for (const [query, expected] of [
  ["guwahati", "Guwahati"],
  ["gauhati", "Guwahati"],
  ["bagibari", "Bagribari (Pt)"],
  ["boikakhat", "Bokakhat"],
  ["chengar", "Chenga"],
  ["palashbari", "Palasbari"],
  ["sibsagar", "Sibsagar"],
  ["gaurisagar", "Gaurisagar Tiniali"],
]) {
  test(`place search finds ${query}`, () => {
    const labels = nearbyMatches(searchKeys(query)).map(item => item.label);
    assert.ok(labels.includes(expected), `${query} results: ${labels.join(", ")}`);
  });
}
