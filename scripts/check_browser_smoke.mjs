/* Load the built site in a real browser and fail on anything the other gates cannot see.
 *
 * Why this exists
 * ---------------
 * On 2026-07-30 the MapLibre migration shipped with the revenue-circle
 * boundaries and the circle-to-gauge tie line missing from the map. Three
 * style-spec violations made `map.addLayer` throw inside the `load` handler, so
 * `addOperationalLayers()` died and everything queued behind it never ran.
 *
 * `npm run check`, `npm test`, `npm run build`, the SEO check and the
 * design-scale check all passed against that map. None of them loads the page.
 * The bug was found by a person opening a browser, which is not a gate.
 *
 * So this check holds the line the others structurally cannot: it opens the
 * built site, forces the detailed atlas, and fails on a console error, an
 * uncaught exception, or a map that finished loading without its gauges.
 *
 * The gauge assertion is the important one. `addGaugeMarkers()` runs on the
 * line after `addOperationalLayers()`, so a throw in the layer code leaves zero
 * `.maplibre-gauge` buttons in the DOM. That is exactly the shape of the
 * regression this script was written for, and it is checked without the
 * component exposing anything for testability.
 *
 * Network
 * -------
 * Every off-origin request is answered locally with a benign stub. Basemap
 * tiles, imagery and glyphs come from OpenStreetMap, ArcGIS and Protomaps, and
 * a CI job has no business hammering any of them on every push — nor should a
 * gate on our own code go red because someone else's tile server is slow. The
 * stub keeps the style loading so `load` still fires and the layer code still
 * runs, which is the part being tested.
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const BUILD = join(ROOT, "build");

/* A page that forces the atlas rather than waiting on a stored preference or a
   connection sniff, so the check exercises the same path every time. */
const PAGE = "/?layer=river";
const READY_SELECTOR = ".maplibre-gauge";
const READY_TIMEOUT_MS = 30000;

const MIME = {
  ".avif": "image/avif",
  ".css": "text/css",
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".pbf": "application/x-protobuf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".woff2": "font/woff2",
};

/* One transparent pixel, PNG. Returned for any off-origin image so MapLibre
   receives a decodable tile instead of a failure it would log. */
const BLANK_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

function serve(directory) {
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, "http://localhost");
    let path = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
    if (path.endsWith("/")) path += "index.html";
    let file = join(directory, path);
    let body;
    try {
      body = await readFile(file);
    } catch {
      try {
        // adapter-static writes /camps/index.html; a request for /camps lands here.
        file = join(directory, path, "index.html");
        body = await readFile(file);
      } catch {
        response.writeHead(404).end("not found");
        return;
      }
    }
    response.writeHead(200, { "content-type": MIME[extname(file)] || "application/octet-stream" });
    response.end(body);
  });
  return new Promise(resolve => {
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

async function main() {
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    console.error(
      "playwright is not installed. Run `npm ci` and `npx playwright install chromium`.",
    );
    return 1;
  }

  const { server, port } = await serve(BUILD);
  const origin = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });

  const problems = [];
  const stubbed = new Set();

  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) {
      await route.continue();
      return;
    }
    stubbed.add(url.host);
    const isImage = /\.(png|jpg|jpeg|webp|avif)(?:$|[?#])/i.test(url.pathname);
    await route.fulfill({
      status: 200,
      contentType: isImage ? "image/png" : "application/octet-stream",
      body: isImage ? BLANK_PNG : Buffer.alloc(0),
    });
  });

  const page = await context.newPage();
  page.on("console", message => {
    if (message.type() !== "error") return;
    problems.push(`console error: ${message.text()}`);
  });
  page.on("pageerror", error => {
    problems.push(`uncaught exception: ${error.message}`);
  });

  let gauges = 0;
  let canvas = null;
  try {
    const response = await page.goto(`${origin}${PAGE}`, { waitUntil: "load" });
    if (!response || !response.ok()) {
      problems.push(`${PAGE} returned ${response ? response.status() : "no response"}`);
    }
    await page.waitForSelector(READY_SELECTOR, { timeout: READY_TIMEOUT_MS });
    gauges = await page.locator(READY_SELECTOR).count();
    canvas = await page.evaluate(() => {
      const element = document.querySelector(".maplibregl-canvas");
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return { width: Math.round(box.width), height: Math.round(box.height) };
    });
  } catch (error) {
    problems.push(
      `the atlas never finished loading: ${error.message.split("\n")[0]}. ` +
        "A throw inside the map's load handler looks exactly like this.",
    );
  }

  await browser.close();
  server.close();

  if (!gauges) {
    problems.push(
      "no gauge markers were drawn. addGaugeMarkers() runs immediately after " +
        "addOperationalLayers(), so this is what a style-spec error in the layer " +
        "code looks like from outside.",
    );
  }
  if (canvas && (canvas.width < 200 || canvas.height < 200)) {
    problems.push(`map canvas collapsed to ${canvas.width}x${canvas.height}`);
  }

  if (problems.length) {
    console.error(`Browser smoke check failed on ${PAGE}:\n`);
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error(
      `\nOff-origin hosts stubbed: ${[...stubbed].sort().join(", ") || "none"}`,
    );
    return 1;
  }

  console.log(
    `Browser smoke check passed: ${PAGE}, ${gauges} gauge markers, ` +
      `canvas ${canvas ? `${canvas.width}x${canvas.height}` : "absent"}, no console errors.`,
  );
  console.log(`Off-origin hosts stubbed: ${[...stubbed].sort().join(", ") || "none"}`);
  return 0;
}

process.exit(await main());
