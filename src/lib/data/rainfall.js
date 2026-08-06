import { cacheFirst, networkFirst, siteUrl } from "./cache.js";

export const RAINFALL_POINTER_URL = "/data/rainfall-current.json";

/* How old the estimate may get before it stops being spoken of in the present
   tense. The artifact carries the run's own threshold; this is the fallback for
   a file published before that field existed. */
const DEFAULT_STALE_AFTER_HOURS = 20;

/* Past this, the estimate is dropped rather than relabelled. The longest window
   this data describes is three days, so an artifact older than that is not late
   news about now — it is a complete account of a period nobody is asking about,
   and on a small screen it would push the river reading down for nothing. */
const DROP_AFTER_HOURS = 72;

function ageHours(asOf, now) {
  const stamp = Date.parse(asOf);
  if (Number.isNaN(stamp)) return null;
  return (now.getTime() - stamp) / 3_600_000;
}

/* The rainfall layer is an addition, never a precondition. Every failure path
   here returns null, and the caller shows the river bulletin exactly as it does
   today. Nothing about rain is allowed to keep a gauge reading off the screen. */
export async function loadRainfall({ now = new Date() } = {}) {
  let pointer;
  try {
    pointer = await networkFirst(RAINFALL_POINTER_URL);
  } catch (_) {
    // No rainfall has been published yet, or the phone is offline and never
    // cached one. Both are ordinary.
    return null;
  }
  if (!pointer?.rainfall_url || !pointer?.as_of) return null;

  const age = ageHours(pointer.as_of, now);
  if (age === null || age > DROP_AFTER_HOURS) return null;

  let artifact;
  try {
    artifact = await cacheFirst(siteUrl(pointer.rainfall_url));
  } catch (_) {
    return null;
  }
  if (artifact?.record !== "circle_rainfall_estimates") return null;
  if (artifact.as_of !== pointer.as_of) {
    // The pointer and the file disagree about which half hour this is. One of
    // them is from a different build, and neither can be trusted to label the
    // other's numbers.
    return null;
  }

  const byLocality = new Map();
  for (const circle of artifact.circles || []) {
    byLocality.set(circle.locality_id, circle);
  }
  return {
    pointer,
    artifact,
    byLocality,
    ageHours: age,
    staleAfterHours: artifact.source?.stale_after_hours ?? DEFAULT_STALE_AFTER_HOURS,
  };
}

/* What the bulletin should say about rain over one circle, or null if it should
   say nothing at all. A circle the pipeline could not compute is deliberately
   *not* null: it gets a sentence saying no estimate is available, because a
   blank space where rainfall belongs reads as "it did not rain". */
export function rainfallFor(loaded, localityId) {
  if (!loaded || !localityId) return null;
  const circle = loaded.byLocality.get(localityId);
  if (!circle) return null;

  const stale = loaded.ageHours > loaded.staleAfterHours;
  const headline = stale && circle.stale_headline ? circle.stale_headline : circle.headline;
  if (!headline) return null;

  return {
    localityId,
    status: stale && circle.status === "estimate" ? "stale_estimate" : circle.status,
    headline,
    estimateNote: loaded.artifact.shared_text?.estimate_note ?? "",
    hedge: loaded.artifact.shared_text?.hedge ?? "",
    attribution: loaded.artifact.source?.attribution ?? "",
    windowHours: circle.window_hours ?? null,
    totalMm: circle.total_precipitation_mm ?? null,
    windows: circle.windows ?? {},
    asOf: loaded.artifact.as_of,
    ageHours: loaded.ageHours,
  };
}
