import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeRenderMode,
  resolveRenderMode,
  shouldOfferFullMode,
} from "../src/lib/mode.js";

test("render mode accepts only the persisted preference values", () => {
  assert.equal(normalizeRenderMode("auto"), "auto");
  assert.equal(normalizeRenderMode("light"), "light");
  assert.equal(normalizeRenderMode("full"), "full");
  assert.equal(normalizeRenderMode("unexpected"), "auto");
});

test("an explicit stored mode wins while automatic mode respects the connection", () => {
  assert.equal(resolveRenderMode("full", { saveData: true }), "full");
  assert.equal(resolveRenderMode("light", { saveData: false }), "light");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "4g" }), "full");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "3g" }), "full");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "slow-2g" }), "light");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "2g", rtt: 1800 }), "light");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "2g", downlink: .1 }), "light");
  assert.equal(resolveRenderMode("auto", { saveData: true, effectiveType: "4g" }), "light");
});

test("automatic mode keeps the map when nothing proves the line is bad", () => {
  // A label with no numbers behind it, and a browser with no connection API at
  // all, both leave the detailed map running. Data saver is the exception here,
  // not the default.
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "2g" }), "full");
  assert.equal(resolveRenderMode("auto", { saveData: false, effectiveType: "2g", rtt: 400 }), "full");
  assert.equal(resolveRenderMode("auto", undefined), "full");
  assert.equal(resolveRenderMode("auto", null), "full");
});

test("the full-mode offer requires undismissed 4g without Save-Data", () => {
  assert.equal(shouldOfferFullMode("auto", { effectiveType: "4g", saveData: false }), true);
  assert.equal(shouldOfferFullMode("auto", { effectiveType: "4g", saveData: true }), false);
  assert.equal(shouldOfferFullMode("auto", { effectiveType: "3g", saveData: false }), false);
  assert.equal(shouldOfferFullMode("auto", { effectiveType: "4g", saveData: false }, true), false);
  assert.equal(shouldOfferFullMode("full", { effectiveType: "4g", saveData: false }), false);
});
