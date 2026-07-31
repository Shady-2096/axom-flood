import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  metadataForPath,
  SITE_URL,
  SOCIAL_IMAGE,
} from "../src/lib/seo.js";

const pages = [
  { pathname: "/", file: "build/index.html" },
  { pathname: "/home/", file: "build/home/index.html" },
  { pathname: "/camps/", file: "build/camps/index.html" },
  { pathname: "/situation/", file: "build/situation/index.html" },
  { pathname: "/emergency/", file: "build/emergency/index.html" },
  { pathname: "/report/", file: "build/report/index.html" },
  { pathname: "/settings/", file: "build/settings/index.html" },
];

function escaped(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function requireMatch(html, pattern, message) {
  assert.match(html, pattern, message);
}

for (const page of pages) {
  const html = readFileSync(page.file, "utf8");
  const metadata = metadataForPath(page.pathname);
  const canonical = `${SITE_URL}${metadata.path}`;

  requireMatch(html, new RegExp(`<title>${escaped(metadata.title)}</title>`), `${page.pathname} title`);
  requireMatch(
    html,
    new RegExp(`<meta name="description" content="${escaped(metadata.description)}"`),
    `${page.pathname} description`,
  );
  requireMatch(
    html,
    new RegExp(`<meta name="robots" content="${escaped(metadata.robots)}"`),
    `${page.pathname} robots`,
  );
  requireMatch(
    html,
    new RegExp(`<link rel="canonical" href="${escaped(canonical)}"`),
    `${page.pathname} canonical`,
  );
  requireMatch(
    html,
    new RegExp(`<meta property="og:url" content="${escaped(canonical)}"`),
    `${page.pathname} Open Graph URL`,
  );
  requireMatch(
    html,
    new RegExp(`<meta property="og:image" content="${escaped(SOCIAL_IMAGE)}"`),
    `${page.pathname} Open Graph image`,
  );
}

const root = readFileSync("build/index.html", "utf8");
assert.doesNotMatch(root, /\{JSON\.stringify\(/, "JSON-LD interpolation leaked into output");
const jsonLd = [...root.matchAll(
  /<script type="application\/ld\+json">(.*?)<\/script>/gs,
)].map(match => JSON.parse(match[1]));
assert.deepEqual(
  new Set(jsonLd.map(block => block["@type"])),
  new Set(["WebSite", "FAQPage"]),
);
assert.match(root, /<h1[^>]*>Clear information on Assam floods\.<\/h1>/);
assert.match(root, /Where can I check Assam flood status today\?/);

const robots = readFileSync("build/robots.txt", "utf8");
const sitemap = readFileSync("build/sitemap.xml", "utf8");
assert.match(robots, /Sitemap: https:\/\/assamflood\.org\/sitemap\.xml/);
for (const pathname of ["/", "/home/", "/camps/", "/situation/", "/emergency/"]) {
  assert.match(sitemap, new RegExp(`<loc>${escaped(`${SITE_URL}${pathname}`)}</loc>`));
}
assert.doesNotMatch(sitemap, /\/report\/|\/settings\//);

console.log(`SEO output verified: ${pages.length} pages, ${jsonLd.length} JSON-LD blocks`);
