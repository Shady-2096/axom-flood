---
name: Axom Flood
description: A calm river observatory for plain-language flood information in Assam.
colors:
  night-ground: "#061c24"
  night-surface: "#0c2b35"
  night-surface-raised: "#123b46"
  night-ink: "#edf5f4"
  night-muted: "#9db2b7"
  day-ground: "#dfeaec"
  day-surface: "#f7faf8"
  day-surface-raised: "#cfe0e2"
  day-ink: "#10272f"
  day-muted: "#526b72"
  river: "#0d7287"
  river-bright: "#75d0df"
  warning: "#d66b24"
  danger: "#a63a27"
  current: "#2f9879"
  map-boundary: "#167f93"
  map-selected: "#073f4b"
  bulletin-glass-night: "rgba(21, 32, 36, .78)"
  bulletin-glass-day: "rgba(232, 235, 234, .78)"
typography:
  ui:
    fontFamily: "Archivo Text, Archivo Fallback, system-ui, sans-serif"
    fontWeight: "400–800"
  numeric:
    fontFamily: "Archivo Broadcast, Archivo Fallback, Arial Narrow, sans-serif"
    fontWeight: 800
  body:
    fontSize: "0.9375rem–1rem"
    lineHeight: "1.5–1.6"
  title:
    fontSize: "1.5rem–2.5rem"
    lineHeight: "1.05–1.15"
rounded:
  marker: "6px"
  navigation: "8px"
  control: "16px"
  panel: "20px"
  sheet: "24px"
  pill: "999px"
---

# Design System: River Observatory

## Direction

Axom Flood is a civic river observatory, not an emergency dashboard and not a lifestyle map.
The interface borrows its clarity from calibrated field instruments: one reading, one plain-language
briefing, visible source and age, and controls grouped by purpose. It should feel steady enough to
trust under stress and specific enough that it could only belong to a river-monitoring service in
Assam.

The homepage is an **Operate** surface. Expression must never hide the place, the river state,
freshness, uncertainty, or the next useful action.

## Composition

### Desktop

- A compact 64px river bar contains brand, primary navigation, theme, and connectivity.
- The map owns the first viewport. It is a working surface, not a background illustration.
- Search sits at the upper left, map tools are consolidated at the upper right, and location is a
  single lower-right control.
- The local flood bulletin is the one substantial object floating over the map.
- “Report local conditions” is the only separate primary call to action in the map viewport.
- Technical detail follows as one calibrated gauge deck. Provenance remains close to the reading,
  not inside a separate oversized card.

### Mobile

- Brand and utilities stay in a compact top bar; primary navigation becomes a bottom dock.
- Search leads, followed by a touchable map band and the bulletin in document flow.
- The bulletin and primary actions use the full available width.
- Technical thresholds stack beneath the current reading without hiding their labels.

## Color

Color strategy is restrained: mineral neutrals, river blue, and safety colors that appear only when
their meaning is real.

### Night

Night mode is for a person checking a phone during a power cut or after dark. Deep blue-black is the
ground; panels separate with tone and one clear edge. River blue marks selection, current
measurement, focus, and primary civic actions. Text is cool white rather than blue-gray.

### Daylight

Daylight mode is authored for high ambient light. The ground is mineral blue-gray, supporting
surfaces carry restrained blue and sage tones, and ink is deep blue-black. It must not become a fog
of white cards. The header remains a deep river field so the map has a deliberate frame.

### Safety

- Green means current, connected, or verified.
- Amber means warning or stale data; it never decorates navigation.
- Red means danger, failure, or emergency.
- Every colored state also carries a label, structure, or symbol that survives grayscale.

## Typography

Archivo Text is the interface voice for headings, body, controls, and labels. Its normal width keeps
the application calm and contemporary. Archivo Broadcast is reserved for the Axom Flood wordmark
and calibrated numerals. It is never used for prose, status explanations, or ordinary section
headings.

- Page and panel titles: normal-width Archivo, 700–800, modest negative tracking.
- Body: 15–16px, maximum 68 characters per line.
- Metadata: 12–14px; never below 12px when it must be read.
- Data labels: 12px, compact and semibold; tracked capitals are limited to instrument metadata.
- Numerals: tabular lining figures; condensed only where a scale or gauge benefits from it.
- Display size is never the sole hierarchy device.

## Surfaces and Depth

There are three planes:

1. **Map sheet** — the geographic working surface.
2. **Briefing surface** — the flood bulletin and location/search controls.
3. **Instrument surface** — the calibrated technical reading.

Reserve panels for those three roles. Supporting notes use spacing instead of more cards or repeated
rules. The calm and no-data bulletin may use neutral optical glass because it sits directly on the
map; its blur, saturation, fine refractive edge, and shadow form one material treatment. Warning,
danger, and extreme bulletins stay opaque. No other content panel adopts glass.

## Controls

- Primary actions are at least 46px high and use 16px continuous corners with optical padding.
- Pills are reserved for small status chips and segmented controls.
- Secondary actions are filled with a quieter surface tone; they are not empty outlines beside a
  filled primary button.
- Icon-only controls have an accessible name and a 44px minimum target.
- Map zoom, reset, and basemap controls live in one dock.
- Hover is a tonal change; press scales to 98%; focus is a 3px river-blue ring.

## The Local Flood Bulletin

The bulletin is the product’s core explanation layer and must always remain.

Its reading order is:

1. Bulletin label and freshness.
2. Place, district, and river.
3. Plain-language status.
4. A short explanation of what the available data does or does not say.
5. The two safest next actions.

A single semantic state mark sits beside the bulletin label. It is filled for a classified reading
and outlined when no current reading is available. Freshness is stated in text, so the mark never
carries meaning alone.

The panel changes materially at warning, danger, and extreme states. Safety fields may become solid
and actions reorder to lead with camps or emergency numbers. Missing data stays a visible,
purposeful state and leads to the official source.

## Technical Reading

Technical data is secondary but not hidden on desktop. It is one coherent gauge deck:

- station and river heading;
- a single current reading;
- warning, danger, highest recorded flood, and trend in a compact two-by-two group;
- one calibrated horizontal track;
- timestamp, source, station code, mapping confidence, and official link.

The current reading is prominent but not theatrical. On daylight surfaces, the measurement area may
use a deep instrument field to create real hierarchy without a giant empty white card.

## Copy and Trust

Use calm, direct sentences that can be read aloud. Never imply:

- that geolocation validates the assigned gauge;
- that a river level is water depth at someone’s house;
- that stale or missing data means safety;
- that Axom Flood replaces CWC, ASDMA, or local authority warnings.

Uncertainty belongs beside the evidence it qualifies. Permanent caveats are quiet context, not
alerts.

## Motion

Motion is sparse and functional. The one authored moment is the map workspace resolving after the
plain-language bulletin has painted. Control hover and press states are short tonal transitions.
Reduced motion removes map animation and all nonessential transitions.

## Quality Floor

- WCAG AA contrast for all text and controls in both themes.
- 44px minimum touch targets.
- Visible keyboard focus and correct semantic controls.
- No nested cards, decorative gradients, colored glows, generic KPI tiles, or icon containers used
  as content. Optical glass is limited to the map bulletin.
- No prose below 14px and no placeholder below 4.5:1 contrast.
- The real longest locality names, stale states, missing data, urgent states, and narrow screens must
  be checked in the browser.
