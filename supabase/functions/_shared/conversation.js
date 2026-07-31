import { COPY_VERSION } from "./copy.js";

export const FLOW_VERSION = 1;
export { COPY_VERSION };

export const DEPTH_CHOICES = Object.freeze([
  Object.freeze({ code: "dry", label: "Dry ground", description: "No flood water here" }),
  Object.freeze({ code: "ankle", label: "Ankle deep", description: "Water around the ankle" }),
  Object.freeze({ code: "knee", label: "Knee deep", description: "Water around the knee" }),
  Object.freeze({
    code: "waist_plus",
    label: "Waist or higher",
    description: "Water at the waist or above",
  }),
]);

const DEPTH_LABELS = Object.freeze(
  Object.fromEntries(DEPTH_CHOICES.map((choice) => [choice.code, choice.label.toLowerCase()])),
);

const RESUMABLE_STATES = new Set([
  "responsibility_notice",
  "awaiting_location",
  "awaiting_depth",
  "review",
]);

const TERMINAL_STATES = new Set(["submitted", "cancelled", "expired"]);

export function initialConversation(overrides = {}) {
  return {
    flowVersion: FLOW_VERSION,
    copyVersion: COPY_VERSION,
    state: "idle",
    resumeState: null,
    location: null,
    localityId: null,
    depthClass: null,
    ...overrides,
  };
}

export function roundLocation(latitude, longitude) {
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    throw new Error("location coordinates must be finite");
  }
  if (lat < 24 || lat > 29.5 || lon < 89 || lon > 97) {
    throw new Error("location is outside the reporting boundary");
  }
  return {
    latitude: Math.round(lat * 1000) / 1000,
    longitude: Math.round(lon * 1000) / 1000,
    precisionFloorM: 50,
    coordinateDecimals: 3,
  };
}

function message(copyKey, parameters = {}) {
  return { type: "message", copyKey, parameters };
}

function actions(choices) {
  return { type: "choices", choices };
}

function locationPromptEffects() {
  return [
    message("location_prompt"),
    { type: "request_location" },
    actions([
      { code: "action:emergency", label: "Emergency help" },
      { code: "action:cancel", label: "Cancel" },
    ]),
  ];
}

function depthPromptEffects() {
  return [
    message("depth_prompt"),
    {
      type: "depth_choices",
      choices: DEPTH_CHOICES.map((choice) => ({
        code: `depth:${choice.code}`,
        label: choice.label,
        description: choice.description,
      })),
    },
    actions([
      { code: "action:emergency", label: "Emergency help" },
      { code: "action:cancel", label: "Cancel" },
    ]),
  ];
}

function reviewEffects(conversation, context = {}) {
  const place = context.place || conversation.localityId || "the shared location";
  return [
    message("review", {
      depth: DEPTH_LABELS[conversation.depthClass] || conversation.depthClass,
      place,
    }),
    actions([
      { code: "action:submit", label: "Submit report" },
      { code: "action:change_depth", label: "Change depth" },
      { code: "action:emergency", label: "Emergency help" },
    ]),
  ];
}

export function promptForState(conversation, context = {}) {
  switch (conversation.state) {
    case "idle":
    case "responsibility_notice":
      return [
        message("responsibility_notice"),
        actions([
          { code: "action:continue", label: "Continue reporting" },
          { code: "action:emergency", label: "Emergency help" },
          { code: "action:cancel", label: "Cancel" },
        ]),
      ];
    case "awaiting_location":
      return locationPromptEffects();
    case "awaiting_depth":
      return depthPromptEffects();
    case "review":
      return reviewEffects(conversation, context);
    case "emergency_guidance":
      return [
        message("emergency"),
        actions([
          { code: "action:continue_report", label: "Continue report" },
          { code: "action:cancel", label: "End" },
        ]),
      ];
    case "submitted":
      return [message("submitted", context)];
    case "cancelled":
      return [message("cancelled")];
    case "expired":
      return [message("expired")];
    default:
      throw new Error(`unknown conversation state: ${conversation.state}`);
  }
}

function emergencyTransition(conversation) {
  const resumeState = RESUMABLE_STATES.has(conversation.state)
    ? conversation.state
    : "responsibility_notice";
  const next = { ...conversation, state: "emergency_guidance", resumeState };
  return {
    conversation: next,
    effects: promptForState(next),
    emergencyGuidanceShown: true,
  };
}

export function transition(conversation, event, context = {}) {
  if (!conversation || conversation.flowVersion !== FLOW_VERSION) {
    throw new Error(`unsupported flow version: ${conversation?.flowVersion}`);
  }
  if (!event || typeof event.type !== "string") {
    throw new Error("event.type is required");
  }

  if (event.type === "emergency_help" && !TERMINAL_STATES.has(conversation.state)) {
    return emergencyTransition(conversation);
  }

  if (event.type === "restart" && TERMINAL_STATES.has(conversation.state)) {
    const next = initialConversation({ state: "responsibility_notice" });
    return { conversation: next, effects: promptForState(next) };
  }

  if (event.type === "cancel" && !TERMINAL_STATES.has(conversation.state)) {
    const next = { ...conversation, state: "cancelled", resumeState: null };
    return { conversation: next, effects: [message("cancelled")] };
  }

  if (event.type === "expire" && !TERMINAL_STATES.has(conversation.state)) {
    const next = { ...conversation, state: "expired", resumeState: null };
    return { conversation: next, effects: [message("expired")] };
  }

  if (event.type === "repeat") {
    return { conversation, effects: promptForState(conversation, context) };
  }

  switch (conversation.state) {
    case "idle": {
      if (event.type !== "begin") break;
      const next = { ...conversation, state: "responsibility_notice" };
      return { conversation: next, effects: promptForState(next) };
    }
    case "responsibility_notice": {
      if (event.type !== "accept_responsibility") break;
      const next = { ...conversation, state: "awaiting_location" };
      return { conversation: next, effects: locationPromptEffects() };
    }
    case "awaiting_location": {
      if (event.type !== "location_shared") break;
      const payload = event.payload || {};
      const location = roundLocation(payload.latitude, payload.longitude);
      const next = {
        ...conversation,
        state: "awaiting_depth",
        location,
        localityId:
          typeof payload.localityId === "string" && payload.localityId
            ? payload.localityId
            : null,
      };
      return { conversation: next, effects: depthPromptEffects() };
    }
    case "awaiting_depth": {
      if (event.type !== "depth_selected") break;
      const depthClass = event.payload?.depthClass;
      if (!DEPTH_LABELS[depthClass]) throw new Error(`invalid depth class: ${depthClass}`);
      const next = { ...conversation, state: "review", depthClass };
      return { conversation: next, effects: reviewEffects(next, context) };
    }
    case "review": {
      if (event.type === "change_depth") {
        const next = { ...conversation, state: "awaiting_depth", depthClass: null };
        return { conversation: next, effects: depthPromptEffects() };
      }
      if (event.type !== "submit") break;
      if (!conversation.location || !conversation.depthClass) {
        throw new Error("cannot submit an incomplete report");
      }
      const next = { ...conversation, state: "submitted", resumeState: null };
      const place = context.place || conversation.localityId || "the shared location";
      const time = context.time || "now";
      return {
        conversation: next,
        effects: [
          {
            type: "persist_report",
            report: {
              location: conversation.location,
              localityId: conversation.localityId,
              depthClass: conversation.depthClass,
            },
          },
          message("submitted", { place, time }),
        ],
      };
    }
    case "emergency_guidance": {
      if (event.type !== "continue_reporting") break;
      const state = RESUMABLE_STATES.has(conversation.resumeState)
        ? conversation.resumeState
        : "responsibility_notice";
      const next = { ...conversation, state, resumeState: null };
      return { conversation: next, effects: promptForState(next, context) };
    }
    default:
      break;
  }

  return {
    conversation,
    effects: [message("invalid"), ...promptForState(conversation, context)],
    invalid: true,
  };
}

export function databaseConversation(row) {
  if (!row) return initialConversation();
  const location =
    row.location_lat == null || row.location_lon == null
      ? null
      : roundLocation(row.location_lat, row.location_lon);
  return initialConversation({
    state: row.state,
    resumeState: row.resume_state,
    location,
    localityId: row.locality_id,
    depthClass: row.depth_class,
  });
}
