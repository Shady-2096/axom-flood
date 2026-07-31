import {
  COPY_VERSION,
  FLOW_VERSION,
  databaseConversation,
  transition,
} from "./conversation.js";
import { hmacHex, identityPeriod, sha256Hex } from "./security.js";

function tenMinuteBucket(at) {
  const value = new Date(at);
  value.setUTCSeconds(0, 0);
  value.setUTCMinutes(Math.floor(value.getUTCMinutes() / 10) * 10);
  return value;
}

function dayBucket(at) {
  const value = new Date(at);
  value.setUTCHours(0, 0, 0, 0);
  return value;
}

async function consume(database, scope, keyHash, start, limit, durationMs) {
  const outcome = await database.consumeRateLimit({
    scope,
    keyHash,
    bucketStart: start.toISOString(),
    limit,
    expiresAt: new Date(start.getTime() + durationMs).toISOString(),
  });
  return outcome?.allowed === true;
}

export async function processConversationEvent({
  channel,
  deliveryId,
  subjectToken,
  networkToken = null,
  event,
  rawRequest,
  database,
  hmacSecret,
  now = new Date(),
}) {
  if (!["web", "telegram", "whatsapp"].includes(channel)) {
    throw new Error("unsupported channel");
  }
  if (!deliveryId || !subjectToken || !event || typeof rawRequest !== "string") {
    throw new Error("incomplete canonical intake");
  }

  const period = identityPeriod(now);
  const subjectHash = await hmacHex(
    hmacSecret,
    `subject\0${period}\0${channel}\0${subjectToken}`,
  );
  const requestHash = await sha256Hex(rawRequest);

  const tenMinutes = tenMinuteBucket(now);
  const day = dayBucket(now);
  const event10m = await consume(
    database,
    "event_10m",
    subjectHash,
    tenMinutes,
    30,
    20 * 60 * 1000,
  );
  const eventDay = await consume(
    database,
    "event_day",
    subjectHash,
    day,
    200,
    48 * 60 * 60 * 1000,
  );
  if (!event10m || !eventDay) {
    return { status: "rate_limited", effects: [], retryAfterSeconds: 600 };
  }

  if (channel === "web" && networkToken) {
    const networkHash = await hmacHex(
      hmacSecret,
      `network\0${day.toISOString().slice(0, 10)}\0${networkToken}`,
    );
    const networkAllowed = await consume(
      database,
      "network_day",
      networkHash,
      day,
      500,
      48 * 60 * 60 * 1000,
    );
    if (!networkAllowed) {
      return { status: "rate_limited", effects: [], retryAfterSeconds: 3600 };
    }
  }

  const row = await database.startConversation({
    channel,
    subjectHash,
    identityPeriod: period,
    flowVersion: FLOW_VERSION,
    copyVersion: COPY_VERSION,
  });
  if (!row?.session_id) throw new Error("conversation session was not returned");

  const conversation = databaseConversation(row);
  const context = {
    place: conversation.localityId || "the shared location",
    time: new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "numeric",
      minute: "2-digit",
    }).format(now),
  };
  const result = transition(conversation, event, context);
  const persistsReport = result.effects.some((effect) => effect.type === "persist_report");
  if (persistsReport) {
    const report10m = await consume(
      database,
      "report_10m",
      subjectHash,
      tenMinutes,
      5,
      20 * 60 * 1000,
    );
    const reportDay = await consume(
      database,
      "report_day",
      subjectHash,
      day,
      20,
      48 * 60 * 60 * 1000,
    );
    if (!report10m || !reportDay) {
      return { status: "rate_limited", effects: [], retryAfterSeconds: 600 };
    }
  }
  const reportId = persistsReport ? crypto.randomUUID() : null;

  const commit = await database.commitStep({
    p_session_id: row.session_id,
    p_expected_lock_version: row.lock_version,
    p_channel: channel,
    p_platform_delivery_id: deliveryId,
    p_subject_hash: subjectHash,
    p_request_hash: requestHash,
    p_new_state: result.conversation.state,
    p_resume_state: result.conversation.resumeState,
    p_location_lon: result.conversation.location?.longitude ?? null,
    p_location_lat: result.conversation.location?.latitude ?? null,
    p_locality_id: result.conversation.localityId,
    p_depth_class: result.conversation.depthClass,
    p_emergency_guidance_shown: result.emergencyGuidanceShown === true,
    p_report_id: reportId,
    p_observed_at: persistsReport ? now.toISOString() : null,
  });

  if (commit?.duplicate === true) {
    return { status: "duplicate", effects: [] };
  }

  return {
    status: result.invalid ? "invalid" : "accepted",
    state: result.conversation.state,
    effects: result.effects,
    reportId,
  };
}
