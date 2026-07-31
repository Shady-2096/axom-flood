import assert from "node:assert/strict";
import test from "node:test";

import watchdogDate from "../scripts/watchdog-date.cjs";

const { previousDateInTimeZone } = watchdogDate;

test("watchdog checks the completed India-runner date after midnight", () => {
  const delayedStart = new Date("2026-07-27T18:56:11Z");
  assert.equal(
    previousDateInTimeZone(delayedStart, "Asia/Kolkata"),
    "2026-07-27",
  );
});

test("watchdog date rolls across month and year boundaries", () => {
  const newYearInIndia = new Date("2026-12-31T20:00:00Z");
  assert.equal(
    previousDateInTimeZone(newYearInIndia, "Asia/Kolkata"),
    "2026-12-31",
  );
});
