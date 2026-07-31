import { createReportingDatabase } from "./database.js";
import { boundedBody } from "./security.js";

export const MAX_BODY_BYTES = 16 * 1024;

export function requiredEnv(name) {
  const value = Deno.env.get(name);
  if (!value) throw new Error(`missing required environment variable: ${name}`);
  return value;
}

export function reportingDatabase() {
  return createReportingDatabase({
    url: requiredEnv("SUPABASE_URL"),
    serviceKey:
      Deno.env.get("SB_SECRET_KEY") || requiredEnv("SUPABASE_SERVICE_ROLE_KEY"),
  });
}

export async function readBoundedBody(request) {
  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > MAX_BODY_BYTES) throw new Error("request body exceeds 16 KiB");
  return boundedBody(await request.text(), MAX_BODY_BYTES);
}

export function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export function safeErrorResponse(error) {
  const message = String(error?.message || "");
  if (
    message.includes("invalid") ||
    message.includes("unsupported") ||
    message.includes("outside") ||
    message.includes("exceeds")
  ) {
    return jsonResponse({ error: "invalid_request" }, 400);
  }
  // Never log the request body, identifiers, coordinates, or platform payload.
  console.error("reporting_function_error", {
    name: error?.name || "Error",
    code: error?.detail || "internal_error",
  });
  return jsonResponse({ error: "temporarily_unavailable" }, 503);
}
