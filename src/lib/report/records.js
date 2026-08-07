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
