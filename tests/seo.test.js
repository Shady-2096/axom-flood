import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  faqItems,
  faqSchema,
  serializeJsonLd,
  websiteSchema,
} from "../src/lib/landing-seo.js";
import {
  metadataForPath,
  routeKey,
  SITE_URL,
} from "../src/lib/seo.js";

test("search metadata uses Assam language and canonical production URLs", () => {
  const landing = metadataForPath("/");
  const river = metadataForPath("/home/");

  assert.match(landing.title, /^Assam Flood Information/);
  assert.match(landing.description, /Assam flood alerts/);
  assert.equal(landing.path, "/");
  assert.equal(river.path, "/home/");
  assert.equal(river.robots, "index,follow,max-image-preview:large");
  assert.equal(SITE_URL, "https://assamflood.org");
});

test("private utility routes stay out of search results", () => {
  assert.equal(routeKey("/settings/"), "settings");
  assert.equal(metadataForPath("/settings/").robots, "noindex,follow");
  assert.equal(metadataForPath("/report/").robots, "noindex,follow");
  assert.equal(metadataForPath("/missing/").robots, "noindex,follow");
});

test("structured data matches visible Assam flood questions", () => {
  assert.equal(websiteSchema.name, "Axom Flood");
  assert.equal(websiteSchema.alternateName, "Assam Flood");
  assert.equal(faqSchema.mainEntity.length, faqItems.length);
  assert.deepEqual(
    faqSchema.mainEntity.map(item => item.name),
    faqItems.map(item => item.question),
  );
  assert.deepEqual(JSON.parse(serializeJsonLd(faqSchema)), faqSchema);
  assert.doesNotMatch(serializeJsonLd({ value: "</script>" }), /</);
});

test("robots and sitemap expose only canonical indexable routes", () => {
  const robots = readFileSync("static/robots.txt", "utf8");
  const sitemap = readFileSync("static/sitemap.xml", "utf8");

  assert.match(robots, /Sitemap: https:\/\/assamflood\.org\/sitemap\.xml/);
  for (const path of ["/", "/home/", "/camps/", "/situation/", "/emergency/"]) {
    assert.match(sitemap, new RegExp(`<loc>${SITE_URL}${path === "/" ? "/" : path}</loc>`));
  }
  assert.doesNotMatch(sitemap, /\/settings\/|\/report\//);
});
