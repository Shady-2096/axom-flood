import { processConversationEvent } from "../_shared/handler.js";
import {
  jsonResponse,
  readBoundedBody,
  reportingDatabase,
  requiredEnv,
  safeErrorResponse,
} from "../_shared/runtime.js";
import { parseWebIntake, renderWebEffects } from "../_shared/web.js";

function corsHeaders(origin: string | null) {
  const allowed = (Deno.env.get("REPORTING_ALLOWED_ORIGINS") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!origin || !allowed.includes(origin)) return null;
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-max-age": "86400",
    vary: "Origin",
  };
}

Deno.serve(async (request) => {
  const origin = request.headers.get("origin");
  const cors = corsHeaders(origin);
  if (!cors) return jsonResponse({ error: "origin_not_allowed" }, 403);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (request.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405, cors);
  }

  try {
    const rawRequest = await readBoundedBody(request);
    const canonical = parseWebIntake(JSON.parse(rawRequest));
    const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
    const result = await processConversationEvent({
      channel: "web",
      ...canonical,
      networkToken: forwarded,
      rawRequest,
      database: reportingDatabase(),
      hmacSecret: requiredEnv("REPORTING_HMAC_SECRET"),
    });
    const status = result.status === "rate_limited" ? 429 : 200;
    return jsonResponse(
      { ...result, effects: renderWebEffects(result.effects) },
      status,
      {
        ...cors,
        ...(result.retryAfterSeconds
          ? { "retry-after": String(result.retryAfterSeconds) }
          : {}),
      },
    );
  } catch (error) {
    const response = safeErrorResponse(error);
    for (const [key, value] of Object.entries(cors)) response.headers.set(key, value);
    return response;
  }
});
