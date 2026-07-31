import { cacheFirst, networkFirst, siteUrl } from "./cache.js";

export const IMPACT_POINTER_URL = "/data/impact-current.json";
export const IMPACT_HISTORY_URL = "/data/impact-history.json";
export const IMPACT_STATUS_URL = "/data/impact-status.json";
export const IMPACT_SEASON_LOSSES_URL = "/data/asdma-season-losses.json";
export const CURRENT_REPORT_DAYS = 3;

export const IMPACT_METRICS = {
  affected_population: {
    label: "Affected people",
    shortLabel: "people",
    unit: "people",
    singularUnit: "person",
    breaks: [1, 1_000, 10_000, 50_000],
  },
  affected_villages: {
    label: "Affected villages",
    shortLabel: "villages",
    unit: "villages",
    singularUnit: "village",
    breaks: [1, 10, 50, 100],
  },
  crop_area_submerged_hectares: {
    label: "Submerged crop area",
    shortLabel: "crop area",
    unit: "hectares",
    singularUnit: "hectare",
    breaks: [0.01, 100, 1_000, 5_000],
  },
  relief_camp_occupants: {
    label: "People in relief camps",
    shortLabel: "camp occupants",
    unit: "people",
    singularUnit: "person",
    breaks: [1, 100, 1_000, 5_000],
  },
  relief_centres_open: {
    label: "Camps and distribution centres",
    shortLabel: "relief centres",
    unit: "centres",
    singularUnit: "centre",
    breaks: [1, 5, 15, 30],
  },
  infrastructure_incidents: {
    label: "Infrastructure incidents",
    shortLabel: "incidents",
    unit: "incidents",
    singularUnit: "incident",
    breaks: [1, 5, 15, 50],
  },
};

export const IMPACT_COLOURS = {
  noData: "#7b8887",
  zero: "#d7ddda",
  stale: "#655f55",
  quarantined: "#744f59",
  // A single-hue ink ramp keeps the administrative layers comparable. The
  // map itself supplies the pale end: positive reports become progressively
  // darker instead of washing every revenue circle in bright cyan.
  steps: ["#78999a", "#486f73", "#28535a", "#0d343d"],
};

const numberFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const integerFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function normalisePlace(value) {
  const normalised = String(value || "")
    .toLocaleLowerCase("en-IN")
    .replaceAll("&", "and")
    .replace(/\bpart\b|\bpt\b/g, "")
    .replace(/[^a-z0-9]+/g, "");
  return {
    kamrupm: "kamrupmetropolitan",
    sissiborgaon: "sissibargaon",
  }[normalised] || normalised;
}

export function placeKey(district, circle = "") {
  return `${normalisePlace(district)}:${normalisePlace(circle)}`;
}

export function reportAgeDays(reportDate, now = new Date()) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const dateValue = Date.parse(`${reportDate}T00:00:00Z`);
  const todayValue = Date.parse(`${today}T00:00:00Z`);
  return Math.max(0, Math.floor((todayValue - dateValue) / 86_400_000));
}

export function reportState(pointer, now = new Date()) {
  if (pointer?.publication_state === "quarantined") return "quarantined";
  if (!pointer?.impact_url) return "no-data";
  return reportAgeDays(pointer.report_date, now) > CURRENT_REPORT_DAYS
    ? "stale"
    : "current";
}

export function metricValue(record, metricKey) {
  if (!record) return null;
  if (metricKey === "relief_centres_open") {
    const camps = record.relief_camps_open;
    const distribution = record.relief_distribution_centres_open;
    return Number.isFinite(camps) && Number.isFinite(distribution)
      ? camps + distribution
      : null;
  }
  const value = record[metricKey];
  return Number.isFinite(value) ? value : null;
}

export function metricColour(value, metricKey, state = "current") {
  if (state === "quarantined") return IMPACT_COLOURS.quarantined;
  if (state === "stale") return IMPACT_COLOURS.stale;
  if (!Number.isFinite(value)) return IMPACT_COLOURS.noData;
  if (value === 0) return IMPACT_COLOURS.zero;
  const breaks = IMPACT_METRICS[metricKey].breaks;
  let index = breaks.findLastIndex(breakpoint => value >= breakpoint);
  index = Math.max(0, Math.min(index, IMPACT_COLOURS.steps.length - 1));
  return IMPACT_COLOURS.steps[index];
}

export function metricFillOpacity(value, metricKey, state = "current", emphasized = false) {
  if (state === "quarantined") return emphasized ? .48 : .28;
  if (state === "stale") return emphasized ? .48 : .26;
  if (!Number.isFinite(value)) return emphasized ? .2 : .06;
  if (value === 0) return emphasized ? .28 : .12;
  const breaks = IMPACT_METRICS[metricKey].breaks;
  const index = Math.max(
    0,
    Math.min(
      breaks.findLastIndex(breakpoint => value >= breakpoint),
      IMPACT_COLOURS.steps.length - 1,
    ),
  );
  return (emphasized ? [.68, .76, .82, .88] : [.52, .62, .72, .82])[index];
}

export function formatMetric(value, metricKey) {
  if (!Number.isFinite(value)) return "Not reported";
  const formatted = Number.isInteger(value)
    ? integerFormatter.format(value)
    : numberFormatter.format(value);
  const metric = IMPACT_METRICS[metricKey];
  const unit = value === 1 ? metric.singularUnit : metric.unit;
  return `${formatted} ${unit}`;
}

export function impactLegendRows(metricKey) {
  const metric = IMPACT_METRICS[metricKey];
  if (!metric) return [];
  return [
    { colour: IMPACT_COLOURS.noData, label: "Not reported" },
    { colour: IMPACT_COLOURS.zero, label: "0 reported" },
    ...metric.breaks.map((lower, index) => {
      const upper = metric.breaks[index + 1];
      return {
        colour: IMPACT_COLOURS.steps[index],
        label: upper === undefined
          ? `${formatMetric(lower, metricKey)} or more`
          : `${formatMetric(lower, metricKey)} to under ${formatMetric(upper, metricKey)}`,
      };
    }),
  ];
}

function countInfrastructure(records, district, circle = null) {
  return records.filter(record => {
    if (normalisePlace(record.district) !== normalisePlace(district)) return false;
    if (circle === null) return true;
    return ["coordinates", "revenue_circle"].includes(record.match_scope)
      && normalisePlace(record.revenue_circle) === normalisePlace(circle);
  }).length;
}

export function aggregateImpact(impact) {
  const infrastructure = impact.infrastructure || [];
  const districts = new Map();
  for (const district of impact.districts || []) {
    districts.set(normalisePlace(district.district), {
      ...district,
      infrastructure_incidents: countInfrastructure(
        infrastructure,
        district.district,
      ),
    });
  }

  const circles = new Map();
  for (const circle of impact.revenue_circles || []) {
    circles.set(placeKey(circle.district, circle.revenue_circle), {
      ...circle,
      infrastructure_incidents: countInfrastructure(
        infrastructure,
        circle.district,
        circle.revenue_circle,
      ),
    });
  }
  return { districts, circles };
}

export function metricAvailable(impact, metricKey) {
  if (metricKey !== "infrastructure_incidents") return true;
  return !(impact.publication?.allowed_fields || [])
    .some(field => field.startsWith("infrastructure_except:"));
}

export function compareSummaries(current, previous) {
  if (!previous) return [];
  return [
    "affected_population",
    "affected_villages",
    "crop_area_submerged_hectares",
    "relief_camp_occupants",
    "relief_centres_open",
  ].map(metricKey => {
    const currentValue = metricValue(current, metricKey);
    const previousValue = metricValue(previous, metricKey);
    return {
      metricKey,
      current: currentValue,
      previous: previousValue,
      change: Number.isFinite(currentValue) && Number.isFinite(previousValue)
        ? currentValue - previousValue
        : null,
    };
  });
}

function validateImpact(pointer, impact) {
  if (impact.revision_id !== pointer.revision_id) {
    throw new Error("The impact pointer and report revision do not match.");
  }
  if (!["validated", "validated_partial"].includes(pointer.publication_state)) {
    const error = new Error("The latest impact report is not approved for publication.");
    error.code = pointer.publication_state === "quarantined" ? "quarantined" : "no-data";
    throw error;
  }
  if (!["validated", "validated_partial"].includes(impact.publication?.state)) {
    throw new Error("The selected impact artifact is not approved for current use.");
  }
}

export function validateImpactStatus(status) {
  const latest = status?.latest_attempt;
  const valid = status?.schema_version === 1
    && /^\d{4}-\d{2}-\d{2}$/.test(latest?.report_date || "")
    && /^[a-f0-9]{64}$/.test(latest?.revision_id || "")
    && ["validated", "validated_partial", "quarantined", "historical", "superseded"]
      .includes(latest?.state)
    && Array.isArray(latest?.failures);
  if (!valid) throw new Error("The ASDMA ingestion status is invalid.");
  return status;
}

export function hasNewerQuarantinedAttempt(status, pointer) {
  const latest = status?.latest_attempt;
  if (latest?.state !== "quarantined" || !pointer) return false;
  return latest.revision_id !== pointer.revision_id
    && latest.report_date >= pointer.report_date;
}

export function validateSeasonLosses(seasonLosses) {
  const confirmedDeaths = seasonLosses?.statewide?.confirmed_deaths;
  const peopleReportedMissing = seasonLosses?.statewide?.people_reported_missing;
  const reports = seasonLosses?.coverage?.reports;
  const unpublishedDates = seasonLosses?.coverage?.unpublished_dates;
  const reportDates = Array.isArray(reports)
    ? new Set(reports.map(report => report.report_date))
    : new Set();
  const reportRowsValid = Array.isArray(reports)
    && reports.length > 0
    && reports.every(report =>
      /^\d{4}-\d{2}-\d{2}$/.test(report?.report_date || "")
      && /^[a-f0-9]{64}$/.test(report?.revision_id || "")
      && Number.isInteger(report?.newly_confirmed_deaths)
      && report.newly_confirmed_deaths >= 0
      && Number.isInteger(report?.newly_reported_missing)
      && report.newly_reported_missing >= 0
      && report.source_artifact_url
        === `data/asdma-source/${report.revision_id}.pdf`
    );
  const totalsMatch = reportRowsValid
    && reports.reduce((sum, report) => sum + report.newly_confirmed_deaths, 0)
      === confirmedDeaths
    && reports.reduce((sum, report) => sum + report.newly_reported_missing, 0)
      === peopleReportedMissing;
  const valid = seasonLosses?.schema_version === 2
    && seasonLosses?.publication?.state === "generated_checkpoint"
    && /^\d{4}-\d{2}-\d{2}$/.test(seasonLosses?.season_start_date || "")
    && /^\d{4}-\d{2}-\d{2}$/.test(seasonLosses?.as_of_date || "")
    && Number.isInteger(confirmedDeaths)
    && confirmedDeaths >= 0
    && Number.isInteger(peopleReportedMissing)
    && peopleReportedMissing >= 0
    && reportRowsValid
    && reportDates.size === reports.length
    && seasonLosses.coverage.daily_reports_reviewed === reports.length
    && seasonLosses.coverage.daily_report_start_date === reports[0].report_date
    && seasonLosses.coverage.daily_report_end_date === reports.at(-1).report_date
    && seasonLosses.season_start_date === reports[0].report_date
    && seasonLosses.as_of_date === reports.at(-1).report_date
    && Array.isArray(unpublishedDates)
    && unpublishedDates.every(date => /^\d{4}-\d{2}-\d{2}$/.test(date))
    && new Set(unpublishedDates).size === unpublishedDates.length
    && unpublishedDates.every(date => !reportDates.has(date))
    && totalsMatch;
  if (!valid) {
    throw new Error("The statewide season loss checkpoint is invalid.");
  }
  return seasonLosses;
}

export async function loadImpactOverlay({ now = new Date() } = {}) {
  let status = null;
  try {
    status = validateImpactStatus(await networkFirst(IMPACT_STATUS_URL));
  } catch (_) {
    // Older deployments may not have the status manifest yet. The valid
    // pointer remains independently usable.
  }

  let pointer;
  try {
    pointer = await networkFirst(IMPACT_POINTER_URL);
  } catch (error) {
    if (status?.latest_attempt?.state === "quarantined") {
      error.code = "quarantined";
      error.message = "The latest ASDMA report was quarantined and no prior validated report is available.";
    }
    throw error;
  }
  const impact = await cacheFirst(siteUrl(pointer.impact_url));
  validateImpact(pointer, impact);
  return {
    status,
    pointer,
    impact,
    state: reportState(pointer, now),
    ageDays: reportAgeDays(pointer.report_date, now),
    newerAttemptQuarantined: hasNewerQuarantinedAttempt(status, pointer),
  };
}

export async function loadImpactSituation({ now = new Date() } = {}) {
  const overlay = await loadImpactOverlay({ now });
  const { pointer, impact } = overlay;

  let history = { reports: [] };
  let seasonLosses = null;
  try {
    history = await networkFirst(IMPACT_HISTORY_URL);
  } catch (_) {
    // The current report remains useful if an older history index is absent.
  }
  try {
    seasonLosses = validateSeasonLosses(
      await networkFirst(IMPACT_SEASON_LOSSES_URL),
    );
  } catch (_) {
    // A missing or invalid checkpoint must not become a zero or hide the daily report.
  }
  const previousEntry = (history.reports || [])
    .filter(report =>
      report.revision_id !== pointer.revision_id
      && report.report_date <= pointer.report_date
      && ["validated", "validated_partial", "historical", "superseded"]
        .includes(report.publication_state)
    )
    .sort((left, right) =>
      right.report_date.localeCompare(left.report_date)
      || right.fetched_at.localeCompare(left.fetched_at)
    )[0];
  let previous = null;
  if (previousEntry?.impact_url) {
    try {
      previous = await cacheFirst(siteUrl(previousEntry.impact_url));
    } catch (_) {
      // Comparison is enhancement-only. Never hide the current official report.
    }
  }

  return {
    ...overlay,
    history,
    seasonLosses,
    previous,
  };
}
