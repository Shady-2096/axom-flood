import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";
import { SOCIAL_IMAGE } from "../src/lib/seo.js";

const layout = readFileSync("src/routes/+layout.svelte", "utf8");
const serviceWorker = readFileSync("src/service-worker.js", "utf8");

test("social preview exposes a large Open Graph image with matching Twitter metadata", () => {
  assert.equal(SOCIAL_IMAGE, "https://assamflood.org/social-card.jpg");
  assert.match(layout, /property="og:image" content=\{SOCIAL_IMAGE\}/);
  assert.match(layout, /property="og:image:width" content="1200"/);
  assert.match(layout, /property="og:image:height" content="630"/);
  assert.match(layout, /name="twitter:card" content="summary_large_image"/);
  assert.match(layout, /name="twitter:image" content=\{SOCIAL_IMAGE\}/);
  assert.ok(statSync("static/social-card.jpg").size < 300 * 1024);
});

test("social preview is not part of the constrained first-visit shell", () => {
  assert.match(serviceWorker, /path !== "\/social-card\.jpg"/);
});
