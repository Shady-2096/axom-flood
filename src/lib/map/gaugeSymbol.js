/* The gauge symbol, defined once for both maps.

   Severity used to be drawn as size — a filled halo growing from 10 to 36 units
   as the river rose. On a map a bigger circle means a bigger area, and the area
   it claimed corresponded to nothing: the legend had to spend a sentence saying
   so. Every gauge now draws at one size, and severity is carried by the fill and
   by a glyph.

   Colour is never the only carrier. Amber and vermilion are exactly the pair that
   collapses for a red-green colour-blind reader, and a flood map has to survive
   being screenshotted and forwarded in greyscale.

   Both maps drew their own version of this and drifted apart: the detailed atlas
   used four hardcoded hex literals that never responded to the theme, one of them
   a danger colour paler than the warning it escalates from, and neither map had
   a symbol for `extreme` at all. */

export const GAUGE_SIZE = 22;
export const GAUGE_RING_RADIUS = 14;

/* Glyphs live in a square 20×20 box because the icon box is square: an 18×20
   viewBox stretched into a square icon turned every disc into a faint ellipse.
   Three strokes is the ceiling at this size — a third chevron reads as texture
   rather than as a third step, so the top state changes shape instead. */
export const GAUGE_GLYPHS = {
  normal: '<path d="M5.6 9.4h8.8M7.2 13h5.6"/>',
  warning: '<path d="M6 12.6 10 8.4l4 4.2"/>',
  danger: '<path d="M6 14.4 10 10.2l4 4.2"/><path d="M6 10 10 5.8l4 4.2"/>',
  extreme:
    '<path d="M10 4.6 16.2 15.4H3.8Z" fill="currentColor" stroke="none"/>'
    + '<path d="M10 9v2.6M10 13.4v.1" stroke="var(--gauge-keyline)" stroke-width="1.7"/>',
};

/* Ring weight, not ring radius. The radius is fixed for every raised state, so
   there is nothing on the ring to measure off the map; only its line weight and
   its pulse change. `normal` gets no ring — a calm gauge does not need to shout,
   and 30-odd calm rings at state-wide zoom would be the heat blob this whole
   change exists to remove. */
export const GAUGE_RINGS = { warning: 1.6, danger: 2.2, extreme: 2.8 };

export const GAUGE_FILLS = {
  normal: "var(--gauge-normal)",
  warning: "var(--gauge-warning)",
  danger: "var(--gauge-danger)",
  extreme: "var(--gauge-extreme)",
};

export const GAUGE_LEGEND = [
  { state: "normal", label: "Below warning level" },
  { state: "warning", label: "Warning level reached" },
  { state: "danger", label: "Danger level reached" },
  // The state both maps used to swallow: above the highest flood ever recorded at
  // this station. It was relabelled as plain danger, drawn in a colour that
  // matched neither its own halo nor the danger dot, and given no legend row.
  { state: "extreme", label: "Above the highest recorded flood" },
  { state: "no-data", label: "No recent reading" },
].map(row => ({ ...row, glyph: GAUGE_GLYPHS[row.state] || "" }));

export function gaugeStatusLabel(state, current) {
  return (
    GAUGE_LEGEND.find(row => row.state === state)?.label
    || (current ? "Below warning level" : "No recent reading")
  );
}
