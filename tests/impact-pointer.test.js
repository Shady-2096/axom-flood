import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const mainPointer = JSON.parse(
  await readFile(new URL("../static/data/current.json", import.meta.url)),
);
const bundle = JSON.parse(
  await readFile(
    new URL(`../static/${mainPointer.content_url}`, import.meta.url),
  ),
);
const impactPointer = JSON.parse(
  await readFile(new URL("../static/data/impact-current.json", import.meta.url)),
);

test("main bundle carries only the stable lazy ASDMA pointer URL", () => {
  assert.equal(bundle.impact_pointer_url, "data/impact-current.json");
  assert.equal("state_summary" in bundle, false);
  assert.equal("infrastructure" in bundle, false);
});

test("ASDMA impact payload stays outside the service-worker shell", async () => {
  const worker = await readFile(
    new URL("../src/service-worker.js", import.meta.url),
    "utf8",
  );
  const shellDeclaration = worker.match(/const SHELL_PATHS = [^;]+;/)?.[0] || "";
  assert.equal(shellDeclaration.includes("impact-current.json"), false);
  assert.equal(worker.includes(impactPointer.impact_url), false);
  assert.match(worker, /MUTABLE_DATA_PATHS[\s\S]*?"\/data\/impact-current\.json"/);
  assert.match(worker, /MUTABLE_DATA_PATHS[\s\S]*?"\/data\/impact-status\.json"/);
  assert.match(worker, /MUTABLE_DATA_PATHS[\s\S]*?"\/data\/asdma-season-losses\.json"/);
  assert.match(
    worker,
    /MUTABLE_DATA_PATHS\.has\(url\.pathname\)/,
  );
});

test("situation data and map stay outside the primary river first paint", async () => {
  const home = await readFile(
    new URL("../build/index.html", import.meta.url),
    "utf8",
  );
  assert.equal(home.includes("impact-current.json"), false);
  assert.equal(home.includes("asdma-season-losses.json"), false);
  assert.equal(home.includes("ImpactMap"), false);
  assert.equal(home.includes("Statewide situation"), false);
});
