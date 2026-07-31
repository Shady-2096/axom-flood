// Drives the shared reporting state machine from the browser.
//
// Telegram and WhatsApp reach that state machine as a chat: one message per
// step. The website does not, and should not — a resident tapping "knee deep"
// during a flood should not be walked through five screens. So the report
// screen keeps its single-screen flow, collects location and depth at once,
// and this module replays those answers into the same server-side machine the
// bots use.
//
// One state machine, one set of server-side validations, three channels. The
// difference is only in how many screens the person sees.
//
// The loop is driven by the state the server reports rather than by a fixed
// script, which is what makes it safe to retry. A sync interrupted after
// `location_shared` resumes at `awaiting_depth` instead of starting again.
//
// Idempotency is deliberately split, because the two kinds of step need
// opposite guarantees:
//
//   - Moving through the flow (`begin`, `accept_responsibility`,
//     `location_shared`, `depth_selected`, `restart`) creates nothing. Those
//     get a delivery id scoped to this sync run, so a retry is free to walk
//     the same ground again.
//   - `submit` is the only step that writes a report, so its delivery id is
//     derived from the record alone and never changes. If a sync succeeds but
//     the browser dies before the record leaves the outbox, the retry's submit
//     comes back deduplicated and we treat the report as already filed rather
//     than writing a second one.

const TERMINAL_STATES = new Set(["submitted", "cancelled", "expired"]);

// Enough headroom for a full run (probe, begin, accept, location, depth,
// submit) plus a restart and a couple of invalid replies, without ever
// spinning if the server keeps reporting a state we cannot advance.
const MAX_STEPS = 12;

function eventForState(state, record) {
  switch (state) {
    case "idle":
      return { type: "begin" };
    case "responsibility_notice":
      return { type: "accept_responsibility" };
    case "awaiting_location":
      return {
        type: "location_shared",
        payload: {
          latitude: record.latitude,
          longitude: record.longitude,
          localityId: record.locality_id || undefined,
        },
      };
    case "awaiting_depth":
      return { type: "depth_selected", payload: { depthClass: record.depth_class } };
    case "review":
      return { type: "submit" };
    case "emergency_guidance":
      // Someone who asked for emergency help still has this report queued.
      // Resuming returns the flow to wherever it was interrupted.
      return { type: "continue_reporting" };
    default:
      return null;
  }
}

async function send(url, deviceToken, deliveryId, event, fetchImpl) {
  const response = await fetchImpl(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      delivery_id: deliveryId,
      device_token: deviceToken,
      event,
    }),
  });
  if (!response.ok) {
    const retryAfter = Number(response.headers?.get?.("retry-after")) || null;
    return { ok: false, httpStatus: response.status, retryAfterSeconds: retryAfter };
  }
  const body = await response.json();
  return { ok: true, ...body };
}

/**
 * Push one queued report through the shared conversation flow.
 *
 * Returns `{ status: "synced" }` once the server holds the report, or
 * `{ status: "queued", reason }` when the record should stay in the outbox for
 * a later attempt. Expected failures never throw, so the caller keeps its
 * local-first behaviour either way.
 */
export async function syncReportConversation(record, url, options = {}) {
  const fetchImpl = options.fetch || globalThis.fetch;
  const runId = String(options.runId || Date.now());
  const deviceToken = record.device_token;
  if (!deviceToken || deviceToken.length < 16 || deviceToken.length > 200) {
    // The endpoint rejects these outright, so stopping here keeps the record
    // queued instead of spending a rate-limit slot on a certain rejection.
    return { status: "queued", reason: "invalid_device_token" };
  }

  const submitDeliveryId = `${record.record_id}:submit`;
  const stepDeliveryId = (state, type) => `${record.record_id}:${runId}:${state}:${type}`;

  // Find out where the server thinks this device is. `repeat` changes nothing,
  // so it is safe to send on every attempt.
  const probe = await send(
    url,
    deviceToken,
    `${record.record_id}:${runId}:probe`,
    { type: "repeat" },
    fetchImpl,
  );
  const first = interpret(probe);
  if (first.stop) return first.outcome;
  let state = first.state;

  for (let step = 0; step < MAX_STEPS; step += 1) {
    if (TERMINAL_STATES.has(state)) {
      // This device finished or abandoned an earlier conversation and the
      // session still sits on that end state. Our report has not been filed
      // yet, so open a fresh one.
      const restart = await send(
        url,
        deviceToken,
        stepDeliveryId(state, "restart"),
        { type: "restart" },
        fetchImpl,
      );
      const resolved = interpret(restart);
      if (resolved.stop) return resolved.outcome;
      state = resolved.state;
      continue;
    }

    const event = eventForState(state, record);
    if (!event) return { status: "queued", reason: "unknown_state", state };

    const submitting = event.type === "submit";
    const result = await send(
      url,
      deviceToken,
      submitting ? submitDeliveryId : stepDeliveryId(state, event.type),
      event,
      fetchImpl,
    );

    if (submitting && result.ok && result.status === "duplicate") {
      // An earlier run already filed this exact record. Filing it again would
      // double-count one person's observation.
      return { status: "synced", deduplicated: true };
    }

    const resolved = interpret(result);
    if (resolved.stop) return resolved.outcome;
    if (submitting && resolved.state === "submitted") return { status: "synced" };
    state = resolved.state;
  }

  return { status: "queued", reason: "flow_did_not_settle", state };
}

// Turns one response into either the next state or a reason to stop.
function interpret(result) {
  if (!result.ok) {
    if (result.httpStatus === 429) {
      return {
        stop: true,
        outcome: {
          status: "queued",
          reason: "rate_limited",
          retryAfterSeconds: result.retryAfterSeconds,
        },
      };
    }
    return {
      stop: true,
      outcome: { status: "queued", reason: "http_error", code: result.httpStatus },
    };
  }
  if (result.status === "rate_limited") {
    return {
      stop: true,
      outcome: {
        status: "queued",
        reason: "rate_limited",
        retryAfterSeconds: result.retryAfterSeconds,
      },
    };
  }
  if (typeof result.state !== "string") {
    // Only submit is expected to come back deduplicated, and the caller has
    // already handled that. Anything else without a state is unusable.
    return { stop: true, outcome: { status: "queued", reason: "no_state_reported" } };
  }
  return { stop: false, state: result.state };
}
