import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPACT_COLOURS,
  aggregateImpact,
  compareSummaries,
  formatMetric,
  hasNewerQuarantinedAttempt,
  impactLegendRows,
  metricColour,
  metricFillOpacity,
  metricValue,
  normalisePlace,
  reportState,
  validateImpactStatus,
  validateSeasonLosses,
} from "../src/lib/data/impact.js";

test("impact metric colours distinguish no data, zero, official steps, and stale", () => {
  assert.equal(metricColour(null, "affected_population"), IMPACT_COLOURS.noData);
  assert.equal(metricColour(0, "affected_population"), IMPACT_COLOURS.zero);
  assert.equal(metricColour(999, "affected_population"), IMPACT_COLOURS.steps[0]);
  assert.equal(metricColour(1_000, "affected_population"), IMPACT_COLOURS.steps[1]);
  assert.equal(metricColour(50_000, "affected_population"), IMPACT_COLOURS.steps[3]);
  assert.equal(
    metricColour(50_000, "affected_population", "quarantined"),
    IMPACT_COLOURS.quarantined,
  );
  assert.ok(!IMPACT_COLOURS.staleSteps.includes(IMPACT_COLOURS.quarantined));
  assert.equal(formatMetric(1, "affected_population"), "1 person");
  assert.equal(formatMetric(1, "affected_villages"), "1 village");
  assert.deepEqual(
    impactLegendRows("affected_population").map(row => row.label),
    [
      "Not reported",
      "0 reported",
      "1 person to under 1,000 people",
      "1,000 people to under 10,000 people",
      "10,000 people to under 50,000 people",
      "50,000 people or more",
    ],
  );
});

test("a historical report still ranks circles instead of flattening the map", () => {
  // Flattening stale reports painted every circle one shade, so all six impact
  // layers rendered identically and unreported circles looked reported.
  assert.equal(
    metricColour(999, "affected_population", "stale"),
    IMPACT_COLOURS.staleSteps[0],
  );
  assert.equal(
    metricColour(50_000, "affected_population", "stale"),
    IMPACT_COLOURS.staleSteps[3],
  );
  assert.notEqual(
    metricColour(999, "affected_population", "stale"),
    metricColour(50_000, "affected_population", "stale"),
  );
  // The historical ramp shares no colour with the current one, so a reader
  // cannot mistake an aged report for today's.
  for (const colour of IMPACT_COLOURS.staleSteps) {
    assert.ok(!IMPACT_COLOURS.steps.includes(colour));
  }
  // An unmentioned circle stays unreported however old the report is.
  assert.equal(metricColour(null, "affected_population", "stale"), IMPACT_COLOURS.noData);
  assert.equal(metricColour(0, "affected_population", "stale"), IMPACT_COLOURS.zero);
  assert.equal(metricFillOpacity(null, "affected_population", "stale"), .06);
  // A historical report reads quieter than a current one at every step.
  for (const value of [1, 1_000, 10_000, 50_000]) {
    assert.ok(
      metricFillOpacity(value, "affected_population", "stale")
        < metricFillOpacity(value, "affected_population", "current"),
    );
  }
  assert.deepEqual(
    impactLegendRows("affected_population", "stale").map(row => row.colour),
    [IMPACT_COLOURS.noData, IMPACT_COLOURS.zero, ...IMPACT_COLOURS.staleSteps],
  );
});

test("impact fills preserve the basemap until a positive report needs emphasis", () => {
  assert.equal(metricFillOpacity(null, "affected_population"), .06);
  assert.equal(metricFillOpacity(0, "affected_population"), .12);
  assert.equal(metricFillOpacity(1, "affected_population"), .52);
  assert.equal(metricFillOpacity(50_000, "affected_population"), .82);
  assert.equal(metricFillOpacity(50_000, "affected_population", "current", true), .88);
  assert.ok(
    metricFillOpacity(0, "affected_population")
      < metricFillOpacity(1, "affected_population"),
  );
});

test("latest quarantine status warns without replacing the prior valid pointer", () => {
  const status = {
    schema_version: 1,
    latest_attempt: {
      report_date: "2026-07-28",
      revision_id: "b".repeat(64),
      state: "quarantined",
      failures: ["district_arithmetic"],
    },
  };
  const pointer = {
    report_date: "2026-07-27",
    revision_id: "a".repeat(64),
  };
  assert.equal(validateImpactStatus(status), status);
  assert.equal(hasNewerQuarantinedAttempt(status, pointer), true);
  assert.equal(
    hasNewerQuarantinedAttempt(status, {
      ...pointer,
      revision_id: status.latest_attempt.revision_id,
    }),
    false,
  );
});

test("impact state keeps quarantine, no data, current, and stale separate", () => {
  const now = new Date("2026-07-29T12:00:00+05:30");
  assert.equal(reportState({ publication_state: "quarantined" }, now), "quarantined");
  assert.equal(reportState({ report_date: "2026-07-29" }, now), "no-data");
  assert.equal(reportState({ report_date: "2026-07-27", impact_url: "data/x" }, now), "current");
  assert.equal(reportState({ report_date: "2026-07-25", impact_url: "data/x" }, now), "stale");
});

test("district and circle aggregation never promotes district-only incidents", () => {
  const impact = {
    districts: [{ district: "Kamrup (M)", affected_population: 10 }],
    revenue_circles: [{
      district: "Kamrup (M)",
      revenue_circle: "Dispur",
      affected_population: 10,
    }],
    infrastructure: [
      { district: "Kamrup (M)", revenue_circle: "Dispur", match_scope: "district" },
      { district: "Kamrup (M)", revenue_circle: "Dispur", match_scope: "revenue_circle" },
    ],
  };
  const result = aggregateImpact(impact);
  assert.equal(result.districts.get(normalisePlace("Kamrup (M)")).infrastructure_incidents, 2);
  assert.equal(
    result.circles.get("kamrupmetropolitan:dispur").infrastructure_incidents,
    1,
  );
});

test("reviewed administrative aliases match impact records without distance inference", () => {
  assert.equal(normalisePlace("Kamrup (M)"), normalisePlace("Kamrup Metropolitan"));
  assert.equal(normalisePlace("Sissiborgaon"), normalisePlace("Sissibargaon"));
});

test("summary comparison uses official values and combines relief centre types", () => {
  const current = {
    affected_population: 90,
    affected_villages: 8,
    crop_area_submerged_hectares: 12.5,
    relief_camp_occupants: 20,
    relief_camps_open: 2,
    relief_distribution_centres_open: 3,
  };
  const previous = {
    affected_population: 100,
    affected_villages: 7,
    crop_area_submerged_hectares: 10,
    relief_camp_occupants: 15,
    relief_camps_open: 1,
    relief_distribution_centres_open: 2,
  };
  const comparison = compareSummaries(current, previous);
  assert.equal(comparison[0].change, -10);
  assert.equal(comparison.at(-1).current, 5);
  assert.equal(metricValue(current, "relief_centres_open"), 5);
});

test("season loss checkpoints fail closed instead of turning invalid data into zero", () => {
  const firstRevision = "a".repeat(64);
  const secondRevision = "b".repeat(64);
  const checkpoint = {
    schema_version: 2,
    season_start_date: "2026-07-27",
    as_of_date: "2026-07-28",
    statewide: {
      confirmed_deaths: 7,
      people_reported_missing: 8,
    },
    coverage: {
      daily_reports_reviewed: 2,
      daily_report_start_date: "2026-07-27",
      daily_report_end_date: "2026-07-28",
      unpublished_dates: [],
      reports: [
        {
          report_date: "2026-07-27",
          revision_id: firstRevision,
          newly_confirmed_deaths: 2,
          newly_reported_missing: 3,
          source_artifact_url: `data/asdma-source/${firstRevision}.pdf`,
        },
        {
          report_date: "2026-07-28",
          revision_id: secondRevision,
          newly_confirmed_deaths: 5,
          newly_reported_missing: 5,
          source_artifact_url: `data/asdma-source/${secondRevision}.pdf`,
        },
      ],
    },
    publication: { state: "generated_checkpoint" },
  };
  assert.equal(validateSeasonLosses(checkpoint), checkpoint);
  assert.throws(
    () => validateSeasonLosses({
      ...checkpoint,
      statewide: { ...checkpoint.statewide, people_reported_missing: -1 },
    }),
    /checkpoint is invalid/,
  );
  assert.throws(
    () => validateSeasonLosses({
      ...checkpoint,
      statewide: { ...checkpoint.statewide, confirmed_deaths: 8 },
    }),
    /checkpoint is invalid/,
  );
});
