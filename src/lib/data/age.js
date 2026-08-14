/* Dating a thing by its own source, rather than by whatever timestamp is nearest.
 *
 * Three screens showed an age. Only one of them had one. The camps screen and
 * the emergency screen both rendered the river gauge's reading age, because that
 * is what `AgeBlock` takes and it was the timestamp in reach — so a camp list
 * read from documents saved eighteen days earlier was headed "3.2 hours old",
 * and so was a helpline number nobody had looked at since July.
 *
 * Every word of that is true about the gauge. None of it is true about the thing
 * it sits above. An age label is a claim about the data underneath it, and
 * borrowing one is the same class of mistake as interpolating a reading.
 */

/* The verb matters as much as the date. "Saved" is when we fetched something,
   "checked" is when a person last looked at it. Neither is "published", which is
   the source's own act and a claim we usually cannot make. */
export function sourceAgeLabel(value, { verb, staleAfterDays, now = new Date() }) {
  const stamp = Date.parse(value ?? "");
  if (Number.isNaN(stamp)) return null;
  const days = Math.floor((now.getTime() - stamp) / 86_400_000);
  const on = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
  }).format(stamp);
  if (days < 1) return { text: `${verb} today`, stale: false };
  if (days === 1) return { text: `${verb} yesterday, ${on}`, stale: false };
  return {
    text: `${verb} ${on}, ${days} days ago`,
    stale: days > staleAfterDays,
  };
}
