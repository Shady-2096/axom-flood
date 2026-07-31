import { renderCopy } from "./copy.js";

const EVENT_TYPES = new Set([
  "begin",
  "accept_responsibility",
  "location_shared",
  "depth_selected",
  "change_depth",
  "submit",
  "emergency_help",
  "continue_reporting",
  "cancel",
  "repeat",
  "restart",
]);

export function parseWebIntake(payload) {
  if (
    typeof payload?.delivery_id !== "string" ||
    !payload.delivery_id ||
    typeof payload?.device_token !== "string" ||
    payload.device_token.length < 16 ||
    payload.device_token.length > 200 ||
    !EVENT_TYPES.has(payload?.event?.type)
  ) {
    throw new Error("invalid web intake payload");
  }
  return {
    deliveryId: payload.delivery_id,
    subjectToken: `web:${payload.device_token}`,
    replyTarget: null,
    event: { type: payload.event.type, payload: payload.event.payload || undefined },
  };
}

export function renderWebEffects(effects) {
  return effects
    .filter((effect) => effect.type !== "persist_report")
    .map((effect) =>
      effect.type === "message"
        ? { ...effect, text: renderCopy(effect.copyKey, effect.parameters) }
        : effect,
    );
}
