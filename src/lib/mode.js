export const RENDER_MODES = ["auto", "light", "full"];

export function normalizeRenderMode(value) {
  return RENDER_MODES.includes(value) ? value : "auto";
}

/* Automatic mode is biased to the detailed map, and the bar for dropping out of
   it is a connection that genuinely cannot carry map tiles — not a cautious
   guess at one. Three things clear that bar:

   - Save-Data. The reader told their own operating system to spend less. That
     is a stated preference, not an inference, and it is honoured directly.
   - slow-2g. The worst tier the Network Information API defines.
   - 2g confirmed by the numbers behind it, so a stale or optimistic label alone
     does not demote a working connection.

   Everything else — 3g, 4g, an unknown type, a browser with no connection API
   at all — gets the full map. A missing signal is not evidence of a bad line,
   and the header switch is one tap away for a reader who disagrees. */
export function resolveRenderMode(preference, connection) {
  const selected = normalizeRenderMode(preference);
  if (selected === "light" || selected === "full") return selected;
  if (!connection) return "full";
  if (connection.saveData === true) return "light";
  if (connection.effectiveType === "slow-2g") return "light";
  if (connection.effectiveType === "2g") return measuredAsSlow(connection) ? "light" : "full";
  return "full";
}

// Round-trip time in milliseconds and downlink in Mbit/s, both as the API
// reports them. Either one alone is enough; a browser that reports neither
// leaves the connection unproven, and unproven means the map still loads.
function measuredAsSlow(connection) {
  const rtt = Number(connection.rtt);
  const downlink = Number(connection.downlink);
  if (Number.isFinite(rtt) && rtt >= 1000) return true;
  return Number.isFinite(downlink) && downlink > 0 && downlink < .25;
}

export function shouldOfferFullMode(preference, connection, dismissed = false) {
  return normalizeRenderMode(preference) === "auto"
    && dismissed !== true
    && connection?.saveData !== true
    && connection?.effectiveType === "4g";
}
