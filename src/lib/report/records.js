// What kinds of record the outbox holds, and which of them can leave the phone.
//
// Separate from outbox.js, which reaches for IndexedDB and the loaded bundle and
// so cannot be imported by a plain node test. The rule below is exactly the sort
// of thing that gets quietly inverted by a later change, so it lives where it
// can be pinned.

/**
 * Whether a queued record has no route off this device.
 *
 * A high-water mark is a recollection of a past flood, not an observation of
 * now. The conversation state machine that the sync loop drives — shared with
 * the Telegram and WhatsApp intake — has no step for one, so there is nowhere
 * to send it. It stays on the phone.
 *
 * This is a deliberate hold, not a queue running late, and the difference
 * matters to the person who wrote it: "it will sync when the network returns"
 * is false on a phone with a perfect connection.
 */
export function isHeldOnDevice(record) {
  return record?.record_type === "hwm";
}

/**
 * Whether a record marked `syncing` was abandoned mid-send and has to be retried.
 *
 * `syncing` is written to IndexedDB before the network call and cleared after it,
 * so it means "a send is in flight" only for as long as the page that started it
 * is alive. Close the tab mid-send — or lose the process to the phone reclaiming
 * memory, which is the ordinary case on the devices this is for — and the flag
 * survives in the database with nothing behind it.
 *
 * The flush loop skips `syncing` records so two sends cannot race. That skip is
 * correct for a send this page is running and wrong for one nothing is running:
 * the report sat there being skipped forever, and it was not counted as queued or
 * held either, so no screen ever mentioned it. A report somebody wrote during a
 * flood, silently stuck on their phone.
 *
 * `inFlightIds` is what this page is actually sending right now. Anything else
 * claiming to be in flight is a leftover, and belongs back in the queue. Deciding
 * it this way rather than by an age threshold keeps it off the device clock,
 * which is not something this project trusts elsewhere either.
 */
export function isAbandonedSync(record, inFlightIds) {
  return record?.status === "syncing" && !inFlightIds.has(record.record_id);
}

/**
 * How long to hold off after the server says it is rate limiting this device.
 *
 * The endpoint counts every event it receives and answers `allowed = count <=
 * limit`, so an attempt made while already over the limit is not refused
 * cheaply — it increments the counter and returns nothing useful. Thirty events
 * per ten minutes sounds generous until you count what one sync run costs: a
 * probe plus a step per stage of the flow.
 *
 * The report screen flushes on mount and on every `online` and `offline` event.
 * A connection that flaps — a weak tower during a flood, which is the condition
 * this whole feature exists for — fires those repeatedly, and each one spent the
 * device's remaining quota on a request the server had already said it would
 * refuse. The screen meanwhile reads "queued reports will sync now".
 *
 * So take the server at its word. `retryAfterSeconds` is what it asked for;
 * `fallbackSeconds` covers a 429 that arrived without the header.
 *
 * Deliberately a duration rather than a wall-clock deadline: it is compared
 * against elapsed time inside one page, so it needs the clock to tick forward
 * and nothing more. These are cheap phones and the date on them is often wrong.
 */
export function retryPauseMs(outcome, { fallbackSeconds = 600 } = {}) {
  if (outcome?.reason !== "rate_limited") return 0;
  const asked = Number(outcome.retryAfterSeconds);
  const seconds = Number.isFinite(asked) && asked > 0 ? asked : fallbackSeconds;
  // An hour is the longest the endpoint asks for (the per-network daily cap).
  return Math.min(seconds, 3600) * 1000;
}
