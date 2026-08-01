import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  NO_GAUGE_DECISION,
  NO_READING_SENTENCE,
  UNGAUGED_LABEL,
  UNGAUGED_SENTENCE,
  isUngauged,
} from "../src/lib/data/coverage.js";

const dataIndex = await readFile(
  new URL("../src/lib/data/index.js", import.meta.url),
  "utf8",
);

const reviewed = decision => ({
  locality_id: "karbi-anglong-silonijan",
  revenue_circle: "Silonijan",
  primary_gauge: decision === NO_GAUGE_DECISION ? null : "023-UBDDIB",
  primary_gauge_mapping: { confidence: "high", reviewed: true, review: { decision } },
});

test("only a reviewed no-gauge decision marks a circle ungauged", () => {
  assert.equal(isUngauged(reviewed(NO_GAUGE_DECISION)), true);
  assert.equal(isUngauged(reviewed("reassign")), false);
  assert.equal(isUngauged(reviewed("keep")), false);
});

test("a circle nobody has reviewed is not ungauged, however bad its mapping", () => {
  // "Nobody has checked" and "nothing fits" are different claims. A circle
  // reading a gauge 101 km away on the wrong river still has a gauge, and
  // saying otherwise would hide the bad mapping instead of fixing it.
  assert.equal(
    isUngauged({
      primary_gauge: "033-UBDDIB",
      primary_gauge_mapping: {
        confidence: "unverified",
        far: true,
        much_nearer_gauge_exists: true,
      },
    }),
    false,
  );
  assert.equal(isUngauged(null), false);
  assert.equal(isUngauged({}), false);
});

test("the two silences do not use each other's words", () => {
  // A gauge that went quiet is worth waiting for. A circle no gauge covers is
  // not, and telling somebody to check back is the failure this copy exists to
  // prevent.
  assert.notEqual(UNGAUGED_SENTENCE, NO_READING_SENTENCE);
  assert.match(UNGAUGED_SENTENCE, /No river gauge sits on the water/);
  assert.doesNotMatch(UNGAUGED_SENTENCE, /recent/i);
  assert.match(UNGAUGED_LABEL, /No gauge covers this circle/);
  // Neither may present itself as an official warning.
  for (const sentence of [UNGAUGED_SENTENCE, NO_READING_SENTENCE]) {
    assert.match(sentence, /official warning source/);
    assert.doesNotMatch(sentence, /\bsafe\b|\bno flood\b/i);
  }
});

test("the bulletin path passes the locality, not the gauge alone", () => {
  // statusInfo and currentSentence cannot see a locality unless it is handed to
  // them, so an ungauged circle would silently fall back to "no recent reading"
  // if a call site dropped the argument.
  assert.match(dataIndex, /export function statusInfo\(gauge, locality = null\)/);
  assert.match(dataIndex, /export function currentSentence\(gauge, locality = null\)/);
  assert.match(dataIndex, /if \(isUngauged\(locality\)\) return UNGAUGED_SENTENCE;/);
});

test("an ungauged circle is never the place shown to a reader who chose nothing", () => {
  // The default view is "the worst reading in Assam". A circle with no reading
  // at all cannot be that, and opening the app on a permanent blank is worse
  // than opening it on somebody else's district.
  assert.match(dataIndex, /if \(isUngauged\(locality\)\) continue;/);
  assert.match(dataIndex, /ungauged: ungauged\.length/);
});
