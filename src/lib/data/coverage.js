/* Whether a circle has a gauge at all, and the words for when it does not.

   Two different silences, and telling them apart is the whole point.

   "No recent reading" means an instrument exists and has gone quiet — check
   back, the number is coming. "No gauge covers this circle" means a reviewer
   looked and found nothing on the water that drains this place: there is no
   number, today or any day, and waiting for one is wasted time. Saying the
   first when the second is true sends somebody back to refresh a page that will
   never fill in.

   Only a reviewed decision produces this state. An unreviewed circle keeps
   whatever gauge it was assigned, because "nobody has checked" is not the same
   claim as "nothing fits".

   Kept out of index.js so it can be imported without SvelteKit's `$lib` alias,
   which is what lets the words themselves be tested rather than grepped for.

   ⚠️ English only, and not yet reviewed in Assamese — the same gap the rest of
   the bulletin copy has. */

/** The decision value in `primary_gauge_mapping.review` that means no gauge fits. */
export const NO_GAUGE_DECISION = "no_suitable_gauge_exists";

export const UNGAUGED_LABEL = "No gauge covers this circle";

export const UNGAUGED_SENTENCE =
  "No river gauge sits on the water that reaches this circle, so there is no "
  + "river level to show here. Check the official warning source before making "
  + "a decision.";

export const NO_READING_SENTENCE =
  "No recent river reading is available for this area. Check the official "
  + "warning source before making a decision.";

/** Has a reviewer decided that nothing on this circle's drainage is gauged? */
export function isUngauged(locality) {
  return locality?.primary_gauge_mapping?.review?.decision === NO_GAUGE_DECISION;
}
