import { processConversationEvent } from "../_shared/handler.js";
import {
  jsonResponse,
  readBoundedBody,
  reportingDatabase,
  requiredEnv,
  safeErrorResponse,
} from "../_shared/runtime.js";
import { verifyHmacSha256 } from "../_shared/security.js";
import { parseWhatsAppWebhook, renderWhatsAppEffects } from "../_shared/whatsapp.js";

async function sendWhatsAppMessages(messages: object[]) {
  const version = requiredEnv("WHATSAPP_GRAPH_VERSION");
  const phoneNumberId = requiredEnv("WHATSAPP_PHONE_NUMBER_ID");
  const accessToken = requiredEnv("WHATSAPP_ACCESS_TOKEN");
  for (const message of messages) {
    const response = await fetch(
      `https://graph.facebook.com/${version}/${phoneNumberId}/messages`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${accessToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(message),
      },
    );
    if (!response.ok) throw new Error("WhatsApp send failed");
  }
}

Deno.serve(async (request) => {
  if (request.method === "GET") {
    const url = new URL(request.url);
    const valid =
      url.searchParams.get("hub.mode") === "subscribe" &&
      url.searchParams.get("hub.verify_token") === requiredEnv("WHATSAPP_VERIFY_TOKEN");
    return valid
      ? new Response(url.searchParams.get("hub.challenge") || "", { status: 200 })
      : jsonResponse({ error: "unauthorized" }, 401);
  }
  if (request.method !== "POST") return jsonResponse({ error: "method_not_allowed" }, 405);

  try {
    const rawRequest = await readBoundedBody(request);
    const signatureValid = await verifyHmacSha256(
      requiredEnv("WHATSAPP_APP_SECRET"),
      rawRequest,
      request.headers.get("x-hub-signature-256"),
    );
    if (!signatureValid) return jsonResponse({ error: "unauthorized" }, 401);

    const canonical = parseWhatsAppWebhook(JSON.parse(rawRequest));
    const result = await processConversationEvent({
      channel: "whatsapp",
      ...canonical,
      rawRequest,
      database: reportingDatabase(),
      hmacSecret: requiredEnv("REPORTING_HMAC_SECRET"),
    });
    if (result.status !== "duplicate" && result.status !== "rate_limited") {
      await sendWhatsAppMessages(
        renderWhatsAppEffects(result.effects, canonical.replyTarget),
      );
    }
    return jsonResponse({ ok: true });
  } catch (error) {
    return safeErrorResponse(error);
  }
});
