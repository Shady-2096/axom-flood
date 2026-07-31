import { processConversationEvent } from "../_shared/handler.js";
import {
  jsonResponse,
  readBoundedBody,
  reportingDatabase,
  requiredEnv,
  safeErrorResponse,
} from "../_shared/runtime.js";
import { parseTelegramUpdate, renderTelegramEffects } from "../_shared/telegram.js";

async function sendTelegramCalls(token: string, calls: Array<{ method: string; body: object }>) {
  for (const call of calls) {
    const response = await fetch(`https://api.telegram.org/bot${token}/${call.method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(call.body),
    });
    if (!response.ok) throw new Error("Telegram send failed");
  }
}

Deno.serve(async (request) => {
  if (request.method !== "POST") return jsonResponse({ error: "method_not_allowed" }, 405);
  try {
    const webhookSecret = requiredEnv("TELEGRAM_WEBHOOK_SECRET");
    if (request.headers.get("x-telegram-bot-api-secret-token") !== webhookSecret) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const rawRequest = await readBoundedBody(request);
    const canonical = parseTelegramUpdate(JSON.parse(rawRequest));
    const result = await processConversationEvent({
      channel: "telegram",
      ...canonical,
      rawRequest,
      database: reportingDatabase(),
      hmacSecret: requiredEnv("REPORTING_HMAC_SECRET"),
    });
    if (result.status !== "duplicate" && result.status !== "rate_limited") {
      const calls = renderTelegramEffects(result.effects, canonical.replyTarget);
      await sendTelegramCalls(requiredEnv("TELEGRAM_BOT_TOKEN"), calls);
    }
    return jsonResponse({ ok: true });
  } catch (error) {
    return safeErrorResponse(error);
  }
});
