class ReportingDatabaseError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ReportingDatabaseError";
    this.status = status;
    this.detail = detail;
  }
}

export function createReportingDatabase({ url, serviceKey, fetchImpl = fetch }) {
  if (!url || !serviceKey) throw new Error("Supabase URL and secret key are required");

  async function rpc(functionName, body) {
    const headers = {
      apikey: serviceKey,
      "content-type": "application/json",
      "content-profile": "api",
      "accept-profile": "api",
    };
    // Legacy service-role keys are JWTs and require the Authorization header.
    // New sb_secret keys authenticate through apikey and must not be sent as JWTs.
    if (serviceKey.split(".").length === 3) {
      headers.authorization = `Bearer ${serviceKey}`;
    }
    const response = await fetchImpl(`${url}/rest/v1/rpc/${functionName}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }
    if (!response.ok) {
      throw new ReportingDatabaseError(
        `reporting RPC ${functionName} failed`,
        response.status,
        data?.code || "database_error",
      );
    }
    return data;
  }

  return {
    async consumeRateLimit({ scope, keyHash, bucketStart, limit, expiresAt }) {
      const rows = await rpc("consume_rate_limit", {
        p_scope: scope,
        p_key_hash: keyHash,
        p_bucket_start: bucketStart,
        p_limit: limit,
        p_expires_at: expiresAt,
      });
      return rows?.[0] || rows;
    },

    async startConversation({ channel, subjectHash, identityPeriod, flowVersion, copyVersion }) {
      const rows = await rpc("start_or_get_conversation", {
        p_channel: channel,
        p_subject_hash: subjectHash,
        p_identity_period: identityPeriod,
        p_flow_version: flowVersion,
        p_copy_version: copyVersion,
      });
      return rows?.[0] || rows;
    },

    async commitStep(parameters) {
      const rows = await rpc("commit_conversation_step", parameters);
      return rows?.[0] || rows;
    },
  };
}

export { ReportingDatabaseError };
