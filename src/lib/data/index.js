import { get, writable } from "svelte/store";
import { cacheFirst, networkFirst, siteUrl } from "./cache.js";
import {
  isUngauged,
  NO_READING_SENTENCE,
  UNGAUGED_LABEL,
  UNGAUGED_SENTENCE,
} from "./coverage.js";
import { store } from "./preferences.js";
import { configureSearch } from "./search.js";

export { geolocationErrorMessage, getPosition } from "./geolocation.js";
export { isUngauged } from "./coverage.js";

export const dataState = writable({
  status: "idle",
  bundle: null,
  pointer: null,
  error: null,
});

let initialization;
let initialized = false;

export async function initializeData({ force = false } = {}) {
  if (initialization) return initialization;
  if (initialized && !force) return get(dataState).bundle;
  initialization = (async () => {
    dataState.update(state => ({
      ...state,
      status: state.bundle ? "ready" : "loading",
      error: null,
    }));
    try {
      // The pointer is mutable and must be checked on the network before an
      // installed cache is considered. The hash-addressed bundle it selects is
      // immutable and remains cache-first.
      const pointer = await networkFirst("/data/current.json");
      const bundle = await cacheFirst(siteUrl(pointer.content_url));
      configureSearch(bundle, pointer);
      dataState.set({ status: "ready", bundle, pointer, error: null });
      initialized = true;
      return bundle;
    } catch (error) {
      const current = get(dataState);
      if (current.bundle) {
        dataState.set({ ...current, status: "ready", error });
        return current.bundle;
      }
      dataState.set({ status: "error", bundle: null, pointer: null, error });
      throw error;
    } finally {
      initialization = null;
    }
  })();
  return initialization;
}

export function getBundle() {
  return get(dataState).bundle;
}

// The place somebody actually chose, and nothing else. Settings reports on this
// one: "not chosen yet" has to stay tellable from "chosen".
export function currentContext() {
  const bundle = getBundle();
  const localityId = store.locality;
  if (!localityId) return null;
  const locality = bundle.localities.find(item => item.locality_id === localityId);
  if (!locality) return null;
  const gauge = bundle.gauges.find(item => item.cwc_station_code === locality.primary_gauge);
  return { locality, gauge };
}

/* The place a reader who has chosen nothing yet is shown.

   Defaulting to a locality was refused here once, for a good reason: a default
   all-clear for a stranger's district reads exactly like an all-clear for your
   own, and that is the one mistake this product cannot make. The reason applies
   to a *quiet* default. This one takes the worst reading in the bundle — the
   highest rung on the water post, freshest first — so the default is a place
   where something is happening, never a green light for somewhere 400 km away.
   Every surface that uses it also labels it as not-yours and offers the two
   ways to fix that. */
export function highestConcernLocality() {
  const bundle = getBundle();
  if (!bundle?.localities?.length) return null;
  const gauges = new Map(bundle.gauges.map(gauge => [gauge.cwc_station_code, gauge]));
  let best = null;
  let bestRank = [-1, -1];
  for (const locality of bundle.localities) {
    // A circle with no gauge can never be the place where something is
    // happening, and standing one in for a reader who has chosen nothing would
    // open the app on a permanent blank.
    if (isUngauged(locality)) continue;
    const gauge = gauges.get(locality.primary_gauge);
    const observed = gauge?.observed_at ? Date.parse(gauge.observed_at) : 0;
    const rank = [statusInfo(gauge).level, Number.isFinite(observed) ? observed : 0];
    if (rank[0] > bestRank[0] || (rank[0] === bestRank[0] && rank[1] > bestRank[1])) {
      best = locality;
      bestRank = rank;
    }
  }
  return best;
}

export function displayContext() {
  const chosen = currentContext();
  if (chosen) return { ...chosen, fallback: false };
  const bundle = getBundle();
  const locality = highestConcernLocality();
  if (!bundle || !locality) return null;
  const gauge = bundle.gauges.find(item => item.cwc_station_code === locality.primary_gauge);
  return { locality, gauge, fallback: true };
}

export function hasSelection() {
  return Boolean(getBundle() && currentContext());
}

export function selectionNote(locality) {
  const selection = store.selection;
  if (!selection) return `${locality.revenue_circle} is saved on this phone.`;
  if (selection.method === "approximate_location") {
    const distance = Number.isFinite(selection.distance_km)
      ? `, nearest circle centre ${selection.distance_km} km away`
      : "";
    return `Chosen from your browser location${distance}. Approximate location does not confirm the river gauge.`;
  }
  if (selection.method === "manual_map") return `${selection.label || locality.revenue_circle} chosen on the map.`;
  if (selection.method === "recent") return `${selection.label || locality.revenue_circle} reopened from your recent places.`;
  return `${selection.label || locality.revenue_circle} entered by name.`;
}

export function resolvedStrings() {
  const bundle = getBundle();
  const catalog = bundle?.i18n?.[store.language];
  if (catalog?.reviewed && catalog.strings) return catalog.strings;
  return bundle?.i18n?.en?.strings || {};
}

export function crowdUrl() {
  const bundle = getBundle();
  if (!bundle?.crowd_url) return null;
  return siteUrl(bundle.crowd_url.startsWith("data/") ? bundle.crowd_url : `data/${bundle.crowd_url}`);
}

export function ageHours(gauge) {
  return Math.max(0, (Date.now() - Date.parse(gauge.observed_at)) / 3600000);
}

export function ageLabel(gauge) {
  const hours = ageHours(gauge);
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min old`;
  if (hours < 24) return `${hours.toFixed(1)} hours old`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} old`;
}

export function isCurrent(gauge) {
  const bundle = getBundle();
  return Boolean(gauge?.observed_at && gauge.level_m != null && gauge.status !== "no_data"
    && ageHours(gauge) <= bundle.stale_after_hours);
}

export function currentSentence(gauge, locality = null) {
  if (isUngauged(locality)) return UNGAUGED_SENTENCE;
  if (!isCurrent(gauge)) return NO_READING_SENTENCE;
  return gauge.sentence_en;
}

export function displaySentence(gauge, locality = null) {
  return currentSentence(gauge, locality)
    .replace(/\s+Official source: https?:\/\/\S+$/, "")
    .replace(/\s+No short-range projection is available\.$/, "");
}

// `level` is the rung this reading occupies on the water post, and it is what
// drives layout: the number of lit segments, the field colour, the size of the
// status headline, and which actions come first. 0 means "we cannot say".
const RIVER_STATES = {
  above_hfl: { state: "extreme", level: 4, label: "Above the highest recorded flood" },
  above_danger: { state: "danger", level: 3, label: "Above danger level" },
  warning: { state: "warning", level: 2, label: "At or above warning level" },
  normal: { state: "normal", level: 1, label: "Below warning level" },
};

/* `state` stays "no-data" for an ungauged circle on purpose. The field colour,
   the glyph, and the action order for "we cannot say" are already right, and a
   fourth quiet state would only ask the CSS to say something the words say
   better. `ungauged` is there for callers that need to know it is permanent. */
export function statusInfo(gauge, locality = null) {
  if (isUngauged(locality)) {
    return { state: "no-data", level: 0, label: UNGAUGED_LABEL, ungauged: true };
  }
  if (!isCurrent(gauge)) return { state: "no-data", level: 0, label: "No current reading" };
  return RIVER_STATES[gauge.status]
    || { state: "no-data", level: 0, label: "Reading not classified" };
}

export function formatLevel(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} m` : "Not available";
}

export function levelNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "Not available";
}

// A one-line read of the whole bundle, for the first-run screen: somebody who
// has not chosen a place yet can still see whether anything is happening.
export function stateOverview() {
  const bundle = getBundle();
  const gauges = new Map(bundle.gauges.map(gauge => [gauge.cwc_station_code, gauge]));
  const counts = { extreme: [], danger: [], warning: [], normal: [], "no-data": [] };
  const ungauged = [];
  for (const locality of bundle.localities) {
    if (isUngauged(locality)) {
      ungauged.push(locality);
      continue;
    }
    const status = statusInfo(gauges.get(locality.primary_gauge));
    counts[status.state].push(locality);
  }
  const raised = [...counts.extreme, ...counts.danger, ...counts.warning];
  return {
    raised,
    // Both denominators stay honest: a circle nobody can gauge is not a circle
    // whose gauge went quiet, and lumping the two would make the network look
    // more broken than it is.
    readable: bundle.localities.length - ungauged.length - counts["no-data"].length,
    ungauged: ungauged.length,
    total: bundle.localities.length,
  };
}

export function formatObserved(value) {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat("en-IN", {
    hour: "numeric", minute: "2-digit", day: "numeric", month: "short",
  }).format(new Date(value));
}

export function trendText(gauge) {
  const trend = Number(gauge?.trend_cm_per_hr);
  if (!Number.isFinite(trend)) return "Not available";
  if (Math.abs(trend) < .5) return "Steady";
  return `${trend > 0 ? "+" : "-"}${Math.abs(trend).toFixed(1)} cm/hr, ${trend > 0 ? "rising" : "falling"}`;
}

export function technicalReading(gauge) {
  const reading = Number(gauge?.level_m);
  const thresholds = [
    ["warning", "Warning level", gauge?.warning_level_m],
    ["danger", "Danger level", gauge?.danger_level_m],
    ["highest", "Highest recorded flood", gauge?.highest_flood_level_m],
  ].map(([key, label, rawValue]) => {
    const numericValue = Number(rawValue);
    return {
      key,
      label,
      rawValue,
      value: formatLevel(rawValue),
      crossed: Number.isFinite(reading)
        && Number.isFinite(numericValue)
        && reading >= numericValue,
    };
  });
  const officialThresholds = thresholds.map(item => Number(item.rawValue));
  const hasCalibratedScale = Number.isFinite(reading)
    && officialThresholds.every(Number.isFinite);
  const thresholdSpan = hasCalibratedScale
    ? Math.max(officialThresholds[2] - officialThresholds[0], 0.5)
    : 1;
  const minimum = hasCalibratedScale ? officialThresholds[0] - thresholdSpan * 0.5 : 0;
  const maximum = hasCalibratedScale ? officialThresholds[2] + thresholdSpan * 0.15 : 1;
  const markerPosition = value => {
    if (!Number.isFinite(Number(value)) || maximum === minimum) return 50;
    return Math.max(3, Math.min(97, ((Number(value) - minimum) / (maximum - minimum)) * 100));
  };
  return {
    reading,
    thresholds,
    hasCalibratedScale,
    markers: [
      ["current", "Current", gauge?.level_m],
      ...thresholds.map(item => [item.key, item.label, item.rawValue]),
    ].map(([key, label, value]) => ({
      key,
      label,
      value,
      position: markerPosition(value),
    })),
  };
}

export function distanceKm(lat1, lon1, lat2, lon2) {
  const toRadians = degrees => degrees * Math.PI / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function nearestLocality(latitude, longitude) {
  const bundle = getBundle();
  return bundle.localities
    .filter(item => Array.isArray(item.centroid) && item.centroid.length === 2)
    .map(item => ({
      locality: item,
      distance: distanceKm(latitude, longitude, item.centroid[1], item.centroid[0]),
    }))
    .sort((a, b) => a.distance - b.distance)[0];
}
