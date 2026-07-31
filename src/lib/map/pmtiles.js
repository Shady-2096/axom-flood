let registered = false;
let protocol;

/**
 * Register PMTiles once for the detailed MapLibre atlas.
 *
 * The protocol is lazy with the atlas chunk. Data-saver mode never imports it.
 * Archives must live on a host that supports CORS and byte-range requests; the
 * service worker deliberately bypasses them.
 */
export async function registerPmtiles(maplibre) {
  if (registered) return protocol;
  const { Protocol } = await import("pmtiles");
  protocol = new Protocol();
  maplibre.addProtocol("pmtiles", protocol.tile);
  registered = true;
  return protocol;
}

export function isPmtilesUrl(value) {
  return typeof value === "string" && (
    value.startsWith("pmtiles://") || /\.pmtiles(?:$|[?#])/i.test(value)
  );
}
