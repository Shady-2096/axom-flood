import { renderCopy } from "./copy.js";

const INTERACTIVE_EVENTS = Object.freeze({
  "action:begin": { type: "begin" },
  "action:continue": { type: "accept_responsibility" },
  "action:continue_report": { type: "continue_reporting" },
  "action:emergency": { type: "emergency_help" },
  "action:cancel": { type: "cancel" },
  "action:submit": { type: "submit" },
  "action:change_depth": { type: "change_depth" },
  "depth:dry": { type: "depth_selected", payload: { depthClass: "dry" } },
  "depth:ankle": { type: "depth_selected", payload: { depthClass: "ankle" } },
  "depth:knee": { type: "depth_selected", payload: { depthClass: "knee" } },
  "depth:waist_plus": {
    type: "depth_selected",
    payload: { depthClass: "waist_plus" },
  },
});

export function parseWhatsAppWebhook(payload) {
  const value = payload?.entry?.[0]?.changes?.[0]?.value;
  const message = value?.messages?.[0];
  if (!message?.id || !message?.from) throw new Error("unsupported WhatsApp webhook");

  let event;
  if (message.type === "location") {
    event = {
      type: "location_shared",
      payload: {
        latitude: message.location.latitude,
        longitude: message.location.longitude,
      },
    };
  } else if (message.type === "interactive") {
    const selection =
      message.interactive?.list_reply?.id || message.interactive?.button_reply?.id;
    event = INTERACTIVE_EVENTS[selection] || { type: "repeat" };
  } else {
    const text = String(message.text?.body || "").trim().toLowerCase();
    if (text === "help" || text === "sos" || text === "rescue") {
      event = { type: "emergency_help" };
    } else if (text === "cancel") {
      event = { type: "cancel" };
    } else if (["start", "report", "hi", "hello"].includes(text)) {
      event = { type: "begin" };
    } else {
      event = { type: "repeat" };
    }
  }

  return {
    deliveryId: message.id,
    subjectToken: `whatsapp:${message.from}`,
    replyTarget: message.from,
    event,
  };
}

function baseMessage(to) {
  return { messaging_product: "whatsapp", recipient_type: "individual", to };
}

export function renderWhatsAppEffects(effects, recipient) {
  const messages = [];
  for (const effect of effects) {
    if (effect.type === "persist_report") continue;
    if (effect.type === "message") {
      messages.push({
        ...baseMessage(recipient),
        type: "text",
        text: { preview_url: false, body: renderCopy(effect.copyKey, effect.parameters) },
      });
    } else if (effect.type === "request_location") {
      messages.push({
        ...baseMessage(recipient),
        type: "text",
        text: {
          preview_url: false,
          body: "Use WhatsApp's attachment menu to share the location where you are standing.",
        },
      });
    } else if (effect.type === "depth_choices") {
      messages.push({
        ...baseMessage(recipient),
        type: "interactive",
        interactive: {
          type: "list",
          body: { text: "Choose the closest water depth where you are now." },
          action: {
            button: "Choose depth",
            sections: [
              {
                title: "Water depth",
                rows: effect.choices.map((choice) => ({
                  id: choice.code,
                  title: choice.label,
                  description: choice.description,
                })),
              },
            ],
          },
        },
      });
    } else if (effect.type === "choices") {
      const visible = effect.choices.slice(0, 3);
      messages.push({
        ...baseMessage(recipient),
        type: "interactive",
        interactive: {
          type: "button",
          body: { text: "Choose an action" },
          action: {
            buttons: visible.map((choice) => ({
              type: "reply",
              reply: { id: choice.code, title: choice.label.slice(0, 20) },
            })),
          },
        },
      });
    }
  }
  return messages;
}
