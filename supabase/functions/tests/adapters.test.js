import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { initialConversation, transition } from "../_shared/conversation.js";
import {
  parseTelegramUpdate,
  renderTelegramEffects,
} from "../_shared/telegram.js";
import {
  parseWhatsAppWebhook,
  renderWhatsAppEffects,
} from "../_shared/whatsapp.js";
import { parseWebIntake, renderWebEffects } from "../_shared/web.js";

async function fixture(name) {
  const url = new URL(`./fixtures/${name}`, import.meta.url);
  return JSON.parse(await readFile(url, "utf8"));
}

test("Telegram fixture maps to canonical begin without retaining profile data", async () => {
  const parsed = parseTelegramUpdate(await fixture("telegram-start.json"));
  assert.equal(parsed.deliveryId, "10001");
  assert.equal(parsed.event.type, "begin");
  assert.equal(parsed.replyTarget, "4242");
  assert.deepEqual(Object.keys(parsed).sort(), [
    "deliveryId",
    "event",
    "replyTarget",
    "subjectToken",
  ]);
});

test("Telegram location stays transient and becomes the canonical location event", async () => {
  const parsed = parseTelegramUpdate(await fixture("telegram-location.json"));
  assert.equal(parsed.event.type, "location_shared");
  assert.equal(parsed.event.payload.latitude, 26.912345);
});

test("WhatsApp list reply maps one stable depth code", async () => {
  const parsed = parseWhatsAppWebhook(await fixture("whatsapp-depth.json"));
  assert.equal(parsed.deliveryId, "wamid.test-depth-1");
  assert.deepEqual(parsed.event, {
    type: "depth_selected",
    payload: { depthClass: "knee" },
  });
});

test("WhatsApp renders four depths as one list, never truncated reply buttons", () => {
  const conversation = initialConversation({
    state: "awaiting_location",
  });
  const result = transition(conversation, {
    type: "location_shared",
    payload: { latitude: 26.912, longitude: 94.681 },
  });
  const messages = renderWhatsAppEffects(result.effects, "test-user");
  const list = messages.find((message) => message.interactive?.type === "list");
  assert.ok(list);
  assert.deepEqual(
    list.interactive.action.sections[0].rows.map((row) => row.id),
    ["depth:dry", "depth:ankle", "depth:knee", "depth:waist_plus"],
  );
});

test("all adapters render the same emergency meaning", () => {
  const result = transition(initialConversation({ state: "review" }), {
    type: "emergency_help",
  });
  const telegram = renderTelegramEffects(result.effects, "test-chat");
  const whatsapp = renderWhatsAppEffects(result.effects, "test-user");
  const web = renderWebEffects(result.effects);
  const telegramText = telegram.find((call) => call.body.text?.includes("1070")).body.text;
  const whatsappText = whatsapp.find((message) => message.text?.body?.includes("1070")).text.body;
  const webText = web.find((effect) => effect.text?.includes("1070")).text;
  assert.equal(telegramText, whatsappText);
  assert.equal(whatsappText, webText);
});

test("web payload uses a bounded transient token and canonical event", () => {
  const parsed = parseWebIntake({
    delivery_id: "00000000-0000-4000-8000-000000000001",
    device_token: "test-device-token-0000000001",
    event: { type: "depth_selected", payload: { depthClass: "ankle" } },
  });
  assert.equal(parsed.event.type, "depth_selected");
  assert.match(parsed.subjectToken, /^web:/);
});
