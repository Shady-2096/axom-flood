import { renderCopy } from "./copy.js";

const CALLBACK_EVENTS = Object.freeze({
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

export function parseTelegramUpdate(update) {
  const deliveryId = String(update?.update_id ?? "");
  const callback = update?.callback_query;
  const message = callback?.message || update?.message;
  const from = callback?.from || update?.message?.from;
  const chatId = message?.chat?.id;
  if (!deliveryId || from?.id == null || chatId == null) {
    throw new Error("unsupported Telegram update");
  }

  let event;
  if (callback) {
    event = CALLBACK_EVENTS[callback.data] || { type: "repeat" };
  } else if (message.location) {
    event = {
      type: "location_shared",
      payload: {
        latitude: message.location.latitude,
        longitude: message.location.longitude,
      },
    };
  } else {
    const text = String(message.text || "").trim().toLowerCase();
    if (text === "/help" || text === "help" || text === "sos" || text === "rescue") {
      event = { type: "emergency_help" };
    } else if (text === "/cancel" || text === "cancel") {
      event = { type: "cancel" };
    } else if (text === "/start" || text === "/report" || text === "report") {
      event = { type: "begin" };
    } else {
      event = { type: "repeat" };
    }
  }

  return {
    deliveryId,
    subjectToken: `telegram:${from.id}`,
    replyTarget: String(chatId),
    event,
  };
}

export function renderTelegramEffects(effects, chatId) {
  const calls = [];
  for (const effect of effects) {
    if (effect.type === "persist_report") continue;
    if (effect.type === "message") {
      calls.push({
        method: "sendMessage",
        body: { chat_id: chatId, text: renderCopy(effect.copyKey, effect.parameters) },
      });
    } else if (effect.type === "request_location") {
      calls.push({
        method: "sendMessage",
        body: {
          chat_id: chatId,
          text: "Share location",
          reply_markup: {
            keyboard: [[{ text: "Share my location", request_location: true }]],
            resize_keyboard: true,
            one_time_keyboard: true,
          },
        },
      });
    } else if (effect.type === "depth_choices" || effect.type === "choices") {
      calls.push({
        method: "sendMessage",
        body: {
          chat_id: chatId,
          text: effect.type === "depth_choices" ? "Choose depth" : "Choose an action",
          reply_markup: {
            inline_keyboard: effect.choices.map((choice) => [
              { text: choice.label, callback_data: choice.code },
            ]),
          },
        },
      });
    }
  }
  return calls;
}
