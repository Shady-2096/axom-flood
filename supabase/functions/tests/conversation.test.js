import assert from "node:assert/strict";
import test from "node:test";

import {
  COPY_VERSION,
  DEPTH_CHOICES,
  FLOW_VERSION,
  initialConversation,
  roundLocation,
  transition,
} from "../_shared/conversation.js";
import { renderCopy } from "../_shared/copy.js";

function advance(conversation, event, context) {
  return transition(conversation, event, context).conversation;
}

test("flow and copy are explicitly versioned", () => {
  assert.equal(FLOW_VERSION, 1);
  assert.equal(COPY_VERSION, 1);
});

test("happy path is deterministic and emits one persist effect", () => {
  let conversation = initialConversation();
  conversation = advance(conversation, { type: "begin" });
  assert.equal(conversation.state, "responsibility_notice");
  conversation = advance(conversation, { type: "accept_responsibility" });
  assert.equal(conversation.state, "awaiting_location");
  conversation = advance(conversation, {
    type: "location_shared",
    payload: { latitude: 26.912345, longitude: 94.680123 },
  });
  assert.deepEqual(conversation.location, {
    latitude: 26.912,
    longitude: 94.68,
    precisionFloorM: 50,
    coordinateDecimals: 3,
  });
  conversation = advance(conversation, {
    type: "depth_selected",
    payload: { depthClass: "knee" },
  });
  assert.equal(conversation.state, "review");
  const submitted = transition(conversation, { type: "submit" }, {
    place: "Silonijan",
    time: "4:32 pm",
  });
  assert.equal(submitted.conversation.state, "submitted");
  assert.equal(
    submitted.effects.filter((effect) => effect.type === "persist_report").length,
    1,
  );
  assert.match(
    renderCopy(
      submitted.effects.find((effect) => effect.type === "message").copyKey,
      submitted.effects.find((effect) => effect.type === "message").parameters,
    ),
    /does not notify emergency responders/,
  );
});

test("all four existing depth classes are the only choices", () => {
  assert.deepEqual(
    DEPTH_CHOICES.map((choice) => choice.code),
    ["dry", "ankle", "knee", "waist_plus"],
  );
});

test("emergency guidance is reachable from every active state and never claims escalation", () => {
  for (const state of [
    "idle",
    "responsibility_notice",
    "awaiting_location",
    "awaiting_depth",
    "review",
  ]) {
    const conversation = initialConversation({ state });
    const result = transition(conversation, { type: "emergency_help" });
    assert.equal(result.conversation.state, "emergency_guidance");
    assert.equal(result.emergencyGuidanceShown, true);
    const copyEffect = result.effects.find((effect) => effect.type === "message");
    const text = renderCopy(copyEffect.copyKey, copyEffect.parameters);
    assert.match(text, /call 1070/i);
    assert.match(text, /I have not sent a rescue request/i);
    assert.doesNotMatch(text, /escalated|notified authorities|responder is reviewing/i);
  }
});

test("emergency branch resumes the exact previous active question", () => {
  const before = initialConversation({
    state: "awaiting_depth",
    location: roundLocation(26.912, 94.681),
  });
  const emergency = transition(before, { type: "emergency_help" }).conversation;
  const resumed = transition(emergency, { type: "continue_reporting" }).conversation;
  assert.equal(resumed.state, "awaiting_depth");
  assert.deepEqual(resumed.location, before.location);
});

test("out-of-bound and non-finite coordinates fail closed", () => {
  assert.throws(() => roundLocation(23.9, 94), /outside/);
  assert.throws(() => roundLocation("not-a-number", 94), /finite/);
});

test("responsibility copy states reporting-only boundary and reviewed number", () => {
  const copy = renderCopy("responsibility_notice");
  assert.match(copy, /not an emergency service/i);
  assert.match(copy, /No responder is monitoring/i);
  assert.match(copy, /1070/);
});
