// Checks that the browser's report sync and the shared server-side flow agree.
//
// The fake endpoint below runs the REAL state machine from
// supabase/functions/_shared/conversation.js. That is the point of the test:
// a mock of our own invention would only prove the client is consistent with
// itself, which is exactly how the two sides drifted apart in the first place
// (the browser posted a flat record; the intake function expects a
// conversation event, so every submission would have been rejected).

import assert from "node:assert/strict";
import test from "node:test";

import {
  initialConversation,
  transition,
} from "../supabase/functions/_shared/conversation.js";
import { syncReportConversation } from "../src/lib/report/conversation.js";

const URL = "https://example.invalid/web-intake";

function record(overrides = {}) {
  return {
    record_id: "rid-1",
    record_type: "crowd",
    latitude: 26.912,
    longitude: 94.68,
    location_precision_m: 50,
    depth_class: "knee",
    locality_id: "karbi-anglong-silonijan",
    submitted_at: "2026-07-30T10:00:00.000Z",
    device_token: "device-token-that-is-long-enough",
    source: "app",
    status: "queued",
    attempts: 0,
    ...overrides,
  };
}

// A stand-in for the Edge Function: real transitions, real delivery-id
// deduplication, plus hooks for the failures the outbox has to survive.
function fakeServer(options = {}) {
  const server = {
    conversation: initialConversation(),
    seenDeliveryIds: new Set(),
    persisted: [],
    requests: [],
    failures: options.failures || [],
  };

  server.fetch = async (url, init) => {
    assert.equal(url, URL);
    const body = JSON.parse(init.body);
    server.requests.push(body);

    const failure = server.failures.shift();
    if (failure) {
      return {
        ok: false,
        status: failure.status,
        headers: {
          get: name => (name === "retry-after" ? (failure.retryAfter ?? null) : null),
        },
      };
    }

    // Mirrors parseWebIntake: shape is validated before anything else.
    assert.equal(typeof body.delivery_id, "string");
    assert.ok(body.delivery_id.length > 0);
    assert.ok(body.device_token.length >= 16 && body.device_token.length <= 200);
    assert.equal(typeof body.event?.type, "string");

    if (server.seenDeliveryIds.has(body.delivery_id)) {
      return json({ status: "duplicate", effects: [] });
    }
    server.seenDeliveryIds.add(body.delivery_id);

    const result = transition(server.conversation, body.event, { place: "Silonijan" });
    server.conversation = result.conversation;
    for (const effect of result.effects) {
      if (effect.type === "persist_report") server.persisted.push(effect.report);
    }
    return json({
      status: result.invalid ? "invalid" : "accepted",
      state: result.conversation.state,
      effects: result.effects.filter(effect => effect.type !== "persist_report"),
    });
  };

  return server;
}

function json(body) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => body,
  };
}

function eventTypes(server) {
  return server.requests.map(request => request.event.type);
}

test("a queued report walks the shared flow and is persisted once", async () => {
  const server = fakeServer();
  const outcome = await syncReportConversation(record(), URL, {
    fetch: server.fetch,
    runId: "run-1",
  });

  assert.equal(outcome.status, "synced");
  assert.equal(server.conversation.state, "submitted");
  assert.equal(server.persisted.length, 1);
  assert.deepEqual(server.persisted[0], {
    location: {
      latitude: 26.912,
      longitude: 94.68,
      precisionFloorM: 50,
      coordinateDecimals: 3,
    },
    localityId: "karbi-anglong-silonijan",
    depthClass: "knee",
  });

  // The flow is driven by server-reported state, not by a fixed script.
  assert.deepEqual(eventTypes(server), [
    "repeat",
    "begin",
    "accept_responsibility",
    "location_shared",
    "depth_selected",
    "submit",
  ]);
});

test("nothing is persisted when the flow is cut short before submit", async () => {
  const server = fakeServer();
  let calls = 0;
  const flaky = async (url, init) => {
    calls += 1;
    // Drop the connection on depth_selected, the 5th call.
    if (calls === 5) throw new Error("network dropped");
    return server.fetch(url, init);
  };

  await assert.rejects(
    () => syncReportConversation(record(), URL, { fetch: flaky, runId: "run-1" }),
    /network dropped/,
  );
  assert.equal(server.persisted.length, 0);
  assert.equal(server.conversation.state, "awaiting_depth");
});

test("an interrupted sync resumes instead of restarting", async () => {
  const server = fakeServer();
  let calls = 0;
  const flaky = async (url, init) => {
    calls += 1;
    if (calls === 5) throw new Error("network dropped");
    return server.fetch(url, init);
  };

  await assert.rejects(
    () => syncReportConversation(record(), URL, { fetch: flaky, runId: "run-1" }),
    /network/,
  );
  assert.equal(server.conversation.state, "awaiting_depth");

  server.requests.length = 0;
  const outcome = await syncReportConversation(record(), URL, {
    fetch: server.fetch,
    runId: "run-2",
  });

  assert.equal(outcome.status, "synced");
  assert.equal(server.persisted.length, 1, "the report is persisted exactly once");
  // It picks up at the server's actual state rather than replaying the flow.
  assert.deepEqual(eventTypes(server), ["repeat", "depth_selected", "submit"]);
});

test("re-syncing a record that already submitted does not file it twice", async () => {
  // The real case: the sync succeeded but the browser closed before the record
  // could be removed from the outbox, so the next flush retries it.
  const server = fakeServer();
  await syncReportConversation(record(), URL, { fetch: server.fetch, runId: "run-1" });
  assert.equal(server.persisted.length, 1);

  server.requests.length = 0;
  const outcome = await syncReportConversation(record(), URL, {
    fetch: server.fetch,
    runId: "run-2",
  });

  assert.equal(outcome.status, "synced");
  assert.equal(outcome.deduplicated, true);
  assert.equal(server.persisted.length, 1, "one observation, one report");
});

test("a second, different report from the same device restarts the session", async () => {
  const server = fakeServer();
  await syncReportConversation(record(), URL, { fetch: server.fetch, runId: "run-1" });
  assert.equal(server.conversation.state, "submitted");

  server.requests.length = 0;
  const outcome = await syncReportConversation(
    record({ record_id: "rid-2", depth_class: "waist_plus" }),
    URL,
    { fetch: server.fetch, runId: "run-2" },
  );

  assert.equal(outcome.status, "synced");
  assert.equal(server.persisted.length, 2);
  assert.equal(server.persisted[1].depthClass, "waist_plus");
  assert.equal(eventTypes(server)[1], "restart");
});

test("rate limiting keeps the record queued and reports retry-after", async () => {
  const server = fakeServer({ failures: [{ status: 429, retryAfter: "600" }] });
  const outcome = await syncReportConversation(record(), URL, {
    fetch: server.fetch,
    runId: "run-1",
  });

  assert.equal(outcome.status, "queued");
  assert.equal(outcome.reason, "rate_limited");
  assert.equal(outcome.retryAfterSeconds, 600);
  assert.equal(server.persisted.length, 0);
});

test("a server error keeps the record queued rather than dropping it", async () => {
  const server = fakeServer({ failures: [{ status: 503 }] });
  const outcome = await syncReportConversation(record(), URL, {
    fetch: server.fetch,
    runId: "run-1",
  });

  assert.equal(outcome.status, "queued");
  assert.equal(outcome.reason, "http_error");
  assert.equal(outcome.code, 503);
  assert.equal(server.persisted.length, 0);
});

test("a device token the endpoint would reject never leaves the device", async () => {
  const server = fakeServer();
  const outcome = await syncReportConversation(record({ device_token: "short" }), URL, {
    fetch: server.fetch,
    runId: "run-1",
  });

  assert.equal(outcome.status, "queued");
  assert.equal(outcome.reason, "invalid_device_token");
  assert.equal(server.requests.length, 0, "no request is sent at all");
});

test("the depth codes the report screen offers are the ones the flow accepts", async () => {
  // Guards the enum agreement both sides depend on.
  for (const depth of ["dry", "ankle", "knee", "waist_plus"]) {
    const server = fakeServer();
    const outcome = await syncReportConversation(
      record({ record_id: `rid-${depth}`, depth_class: depth }),
      URL,
      { fetch: server.fetch, runId: "run-1" },
    );
    assert.equal(outcome.status, "synced", `depth ${depth} should be accepted`);
    assert.equal(server.persisted[0].depthClass, depth);
  }
});

test("a coordinate outside the reporting boundary is refused by the flow", async () => {
  // The client rounds coordinates; the server independently enforces bounds.
  const server = fakeServer();
  await assert.rejects(
    () =>
      syncReportConversation(record({ latitude: 12.97, longitude: 77.59 }), URL, {
        fetch: server.fetch,
        runId: "run-1",
      }),
    /outside the reporting boundary/,
  );
  assert.equal(server.persisted.length, 0);
});
