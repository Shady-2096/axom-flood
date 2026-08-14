/**
 * What the site is actually showing right now, and what has gone dark.
 *
 * Why this exists
 * ---------------
 * Every layer here degrades honestly on screen. Rainfall past 72 hours is
 * dropped rather than shown as news; an ASDMA report older than three days is
 * repainted in a colour the map uses for nothing else. A reader is never misled.
 *
 * Nobody is ever told, though. Rainfall stopped publishing on 2026-08-07,
 * crossed 72 hours three days later, and vanished from every bulletin in Assam.
 * The ASDMA impact layer has been showing a report from 2026-07-27 for over two
 * weeks. Both are working exactly as designed, and both were found by opening
 * the site and looking, which is not a monitoring strategy.
 *
 * So: one command that answers "what does a reader see today".
 *
 * It reads `static/data/` -- the files the site downloads, not the pipeline's
 * working directory -- and it decides visibility by calling the site's own
 * functions rather than copying their thresholds. A check that keeps its own
 * copy of a number drifts from the page and then reports confidently about a
 * page that is doing something else.
 *
 * Exit codes
 * ----------
 * Plain run reports and exits 0. `--check` exits 1 if any layer is dark.
 *
 * ⚠️ `--check` is deliberately *not* in the CI chain. ASDMA is documented as
 * gappy -- it is blocked from cloud hosts and fetched from one Mac -- and an
 * upstream agency having a quiet week must not be able to fail a build that
 * changes a stylesheet. Run it when you want to know, or on a schedule that can
 * notify someone.
 */

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { rainfallVisibility, ageHours } from "../src/lib/data/rainfall.js";
import { reportState, reportAgeDays, CURRENT_REPORT_DAYS } from "../src/lib/data/impact.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const STATIC = join(ROOT, "static", "data");
const NOW = new Date();

function readJson(name) {
  const path = join(STATIC, name);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf8"));
}

/** Follow a pointer's url field to the artifact it names. */
function follow(pointer, field) {
  if (!pointer?.[field]) return null;
  return readJson(pointer[field].replace(/^data\//, ""));
}

function hours(value) {
  if (value === null || !Number.isFinite(value)) return "—";
  if (value < 48) return `${value.toFixed(1)} h`;
  return `${(value / 24).toFixed(1)} d`;
}

const layers = [];

/* The river bulletin. This is the one people came for, and the only layer whose
   absence is not a degraded experience but no product at all. */
{
  const pointer = readJson("current.json");
  const content = follow(pointer, "content_url");
  const age = pointer ? ageHours(pointer.generated_at, NOW) : null;
  const staleAfter = content?.stale_after_hours ?? 6;
  // A gauge reading is aged per gauge, not per bundle, so the honest bundle-level
  // question is whether any gauge is still current enough to be drawn as a
  // reading rather than as "no recent reading".
  const current = (content?.gauges || []).filter(
    gauge => gauge.observed_at && ageHours(gauge.observed_at, NOW) <= staleAfter,
  ).length;
  layers.push({
    name: "River levels (CWC)",
    published: pointer?.generated_at ?? null,
    age,
    sees:
      !content ? "nothing published"
      : current === 0 ? "every gauge reads no recent reading"
      : `${current} of ${content.gauges.length} gauges reading`,
    dark: !content || current === 0,
    every: "2 hours, Cloud Run",
  });
}

/* Satellite rainfall. Context for circles no gauge serves. */
{
  const pointer = readJson("rainfall-current.json");
  const artifact = follow(pointer, "rainfall_url");
  const age = pointer ? ageHours(pointer.as_of, NOW) : null;
  const staleAfter = artifact?.source?.stale_after_hours;
  const visibility = pointer ? rainfallVisibility(age, staleAfter) : "dropped";
  layers.push({
    name: "Rainfall (NASA IMERG)",
    published: pointer?.as_of ?? null,
    age,
    sees:
      visibility === "dropped" ? "no rainfall line at all"
      : visibility === "stale" ? `estimate, marked "nothing newer has arrived"`
      : `estimate for ${artifact?.circles?.length ?? "?"} circles`,
    dark: visibility === "dropped",
    every: "2 hours, Cloud Run",
  });
}

/* ASDMA flood impact. Affected people, villages, crop, camps. */
{
  const pointer = readJson("impact-current.json");
  const state = pointer ? reportState(pointer, NOW) : "no-data";
  const days = pointer?.report_date ? reportAgeDays(pointer.report_date, NOW) : null;
  layers.push({
    name: "Flood impact (ASDMA)",
    published: pointer?.report_date ?? null,
    age: days === null ? null : days * 24,
    sees:
      state === "no-data" ? "no impact layer"
      : state === "quarantined" ? "quarantined, previous report held"
      : state === "stale" ? `report from ${pointer.report_date}, painted as historical`
      : "current report",
    // Painted as historical is honest, not dark. Dark is when the map has
    // nothing to draw, or the report is old enough that nobody would call it a
    // picture of now.
    dark: state === "no-data" || (days !== null && days > CURRENT_REPORT_DAYS * 3),
    every: "20:00 and 22:00, from the owner's Mac",
  });
}

const width = Math.max(...layers.map(layer => layer.name.length));
const dark = layers.filter(layer => layer.dark);

console.log(`As of ${NOW.toISOString()}\n`);
for (const layer of layers) {
  const flag = layer.dark ? "DARK " : "     ";
  console.log(
    `${flag}${layer.name.padEnd(width)}  ${hours(layer.age).padStart(7)} old  ${layer.sees}`,
  );
  // Line up under the "sees" column: flag(5) + name + 2 + age(7) + " old  "(6).
  console.log(`${" ".repeat(width + 20)}published ${layer.published ?? "never"}` +
    `, expected every ${layer.every}`);
}

if (dark.length === 0) {
  console.log("\nEvery layer the site reads is publishing.");
} else {
  console.log(`\n${dark.length} of ${layers.length} layers are dark: ` +
    dark.map(layer => layer.name).join(", "));
  console.log("A reader sees the site working, with those layers simply absent.");
}

if (process.argv.includes("--check") && dark.length > 0) process.exit(1);
