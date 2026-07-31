# Axom Flood

**Official Assam river-gauge data, turned into a plain sentence anyone can read and forward.**

Live at **[assamflood.org](https://assamflood.org)**.

When the Brahmaputra and its tributaries rise, the official numbers exist — the
Central Water Commission publishes gauge readings, danger levels, and forecasts
every hour. But they're buried in a dashboard, in hydrology terms, on a page that
assumes you already know what "reduced level above datum" means.

Axom Flood reads those official numbers and writes one sentence: which river,
where, how high, rising or falling, and how that compares to the danger level.
It's built for a person on a phone, on a bad connection, who does not speak
hydrology — which is most people in Assam during a flood.

> ⚠️ **This is not an official warning system.** Axom Flood translates public
> data from CWC, ASDMA, and other agencies. It does not replace them. For
> emergencies, contact ASDMA at **1070**.

---

## What it does

- **Reads official river gauges** from the Central Water Commission every 2 hours
  and turns each reading into plain language.
- **Compares to published thresholds** — Warning, Danger, and Highest Flood
  Level — so "56.3 m" becomes "just below the danger mark and rising".
- **Never invents a number.** Missing or stale data is shown as *no data*, never
  as a guess or an interpolation. If a gauge goes silent, we say so.
- **Works on a bad connection.** It's an installable PWA. A lightweight
  data-saver mode drops the heavy map layers for constrained connections.
- **Maps the situation** — a full Assam river atlas with gauge stations, revenue
  circles, and relief-camp locations for people on capable connections.
- **Shows relief camps and helplines** matched from district disaster-management
  sources.

Every translated sentence keeps its source and timestamp attached. Nothing we
show is ever presented as an official warning.

---

## How it works

Two halves live in one repository.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Official        │     │  Python pipeline  │     │  SvelteKit PWA   │
│  sources         │ ──▶ │  clean, validate, │ ──▶ │  reads bundles,  │
│  (CWC, ASDMA…)   │     │  version, publish │     │  renders the     │
│                  │     │  JSON bundles     │     │  plain sentence  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Ingest.** Python adapters (`src/axom_flood/`) pull from each official
   source, one folder per source.
2. **Validate and version.** Raw payloads are addressed by SHA-256 and never
   overwritten. Derived data carries the source URL, a timestamp, and an
   extractor version, so a parser fix never rewrites history.
3. **Publish.** A build step writes content-hashed JSON bundles into
   `static/data/`. A small mutable pointer (`current.json`) tells the site which
   bundle is live, so content and alerts update without redeploying the app.
4. **Serve.** The SvelteKit site (`src/routes/`, `src/lib/`) fetches those
   bundles and renders the sentence, the map, camps, and helplines.

### The refresh loop

The critical gauge feed refreshes on its own. A **Cloud Run Job in Google
Cloud's Mumbai region** runs every 2 hours: it clones a fresh `main`, ingests the
CWC feed, rebuilds the bundle, and pushes the commit. That push triggers a Vercel
deploy, and the live site moves to the new data. No human in the loop.

---

## Data sources

Honesty about sources is the whole point of the project, so here is the real
state of each one.

| Source | Role | State |
|---|---|---|
| **CWC FFS** (`ffs.india-water.gov.in`) | **Primary.** River levels, thresholds, forecasts. | Live. Refreshed every 2 hours. |
| **ASDMA bulletins** | Official flood-impact reports (affected villages, camps, damage). | Live, but blocked from cloud hosts — fetched from a residential machine on a schedule. Expect gaps. |
| **OpenStreetMap** | Place names and district / revenue-circle boundaries the census doesn't have. | Live. ODbL — shipped data carries visible attribution. |
| **Census 2011** | Administrative unit names and membership. | Static. Reflects 2011 boundaries; never contains post-2011 places. |
| **UDISE** | School locations, used to match relief camps. | 2021 community snapshot. Labelled stale; not used for live navigation. |
| **NWDP gauges** | Secondary gauge cross-check. | Reachable but its last real reading is old — emitted as `no_data`. |
| **SMART AXOM — water levels** (`smartaxom.nesdr.gov.in`) | Reference. The station-to-revenue-circle name crosswalk CWC doesn't expose. | Live, but just a 1-hour-stale mirror of CWC's levels. We use it **only** for the station roster and circle names — never for live readings. |
| **SMART AXOM / FLEWS — alerts** (`api.nesdr.gov.in`) | Per-circle flood severity (would be ideal). | ☠️ **Dead since Aug 2023.** The endpoint still responds but every row is frozen at `2023-08-26`. Emitted as `no_data`, never planned around. |

The CWC contract is unauthenticated but undocumented — it's the same feed the
official site's own dashboard reads. Because CWC publishes no stability
guarantee, field-level validation and drift detection are part of the adapter's
job. The endpoints and every field relied on are documented in
[`src/axom_flood/cwc/client.py`](src/axom_flood/cwc/client.py).

---

## The rules we hold ourselves to

These are non-negotiable, because a flood alert that lies is worse than none.

- **Never invent a reading.** Stale and missing data are said out loud as
  `no_data` — never interpolated or filled with a plausible-looking guess.
- **Never call our output an official warning.** We translate; we don't warn.
- **A gauge's status comes from its own reading** against published thresholds,
  never from an upstream convenience field that might be null.
- **A silent gauge is not an all-clear.** A station that vanishes from the feed
  keeps its last reading, is flagged as missing, and ages into `no_data` — it is
  never quietly dropped, because an absent gauge reads like a gauge that's fine.
- **Say what's unreviewed.** Unreviewed gauge-to-circle mappings, unverified camp
  locations, and the not-yet-reviewed Assamese translations are never shown as
  approved. Assamese is offered but falls back to reviewed English until the copy
  is signed off.

---

## Tech stack

- **Data pipeline:** Python 3.11+, managed with [uv](https://docs.astral.sh/uv/).
  A `axom-flood` CLI drives every source.
- **Website:** [SvelteKit](https://kit.svelte.dev/) with `adapter-static`, built
  with Vite. Ships as an installable, offline-capable PWA.
- **Map:** [MapLibre GL](https://maplibre.org/) with PMTiles for the detailed
  Assam atlas.
- **Hosting:** Vercel (site) + a Google Cloud Run Job in Mumbai (the 2-hourly
  data refresh).

---

## Repository layout

```
Axom-floods/
├── src/axom_flood/   Python. Data pipelines, one folder per source.
├── src/routes/       The site's pages (home, camps, report, emergency, settings, situation).
├── src/lib/          Site components, map code, data loading.
├── scripts/          Build scripts and CI checks.
├── config/           Hand-maintained reference data (localities, gauge mappings, circle shapes).
├── data/             Raw + processed source data. Append-only, hash-addressed.
├── static/data/      The JSON bundles the live site downloads.
├── tests/            Python and JS tests.
├── ops/cloudrun/     The job that refreshes gauges every 2 hours.
└── docs/             Data-source provenance and working notes.
```

---

## Run it locally

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22+.

```bash
# Website
npm ci
npm run dev        # dev server
npm run build      # production build into build/
npm run preview    # serve the built site

# Data pipeline
uv sync --extra dev --locked
uv run axom-flood cwc --backfill-hours 12    # ingest the primary gauge feed
uv run python scripts/build_pwa_bundle.py    # rebuild the site's data bundle
```

The site reads `static/data/current.json`, then immutable content-hashed
bundles. Publishing a new pointer and bundle updates alerts, camps, helplines,
and translations without touching the app shell.

### Before you push

CI runs these in order — a lint break fails the whole run before any test, so run
the full set:

```bash
npm ci && npm run check && npm test && npm run build && npm run check:seo && npm run check:browser && node scripts/check_design_scale.mjs && uv run ruff check . && uv run pytest && uv run python scripts/check_pwa_budget.py
```

`check:browser` loads the built site in headless Chromium and fails on any
console error — it exists because a map rewrite once shipped broken while every
other gate passed.

---

## Contributing

Contributions are welcome, and **not all of the highest-value work is code.**

### Review the river maps (no coding, no hydrology degree needed)

The single biggest open task is confirming which river each revenue circle drains
— the mapping that decides which gauge speaks for which place. Some of these are
still auto-assigned by distance, which is wrong across Assam's braided rivers and
hills.

These questions are written so anyone who **knows Assam's rivers** can answer
them — "which river drains this circle", "which river is this gauge on" — with no
discharge modelling involved. If that's you, see
[`docs/gauge-topology-questions.md`](docs/gauge-topology-questions.md). Your
qualification is recorded honestly — a river reviewer's answer is never written
up as a hydrologist sign-off.

### Review the Assamese translation

The Assamese copy is drafted but unreviewed, so the site currently falls back to
English. A fluent reviewer would unblock the language the audience actually
reads.

### Code

- **Adding a data source?** Keep the source URL and timestamp on everything
  derived from it. Add a fixture test, and bump the extractor/schema version if
  the output contract changes.
- **Never overwrite a raw payload** — they're hash-addressed and append-only.
- **Detailed mode has no data budget**; only data-saver mode is size-constrained.
  The CI budget check guards the app shell, not the map layers.
- Run the full CI command above before pushing.

Open an issue to discuss anything substantial before you start.

---

## License and attribution

The code in this repository is licensed under the
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). In short: you're
free to use, modify, and redistribute it, but if you run a modified version as a
network service, you must make your source available to its users. This keeps a
public-good tool from being quietly forked into a closed clone.

### Data

- **OpenStreetMap** data is © OpenStreetMap contributors, used under the
  [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).
  Shipped data carries visible attribution.
- CWC, ASDMA, Census, and UDISE data belong to their respective agencies. Axom
  Flood redistributes derived, translated views with provenance attached and does
  not claim ownership of the underlying data.

---

## Disclaimer

Axom Flood is an independent, volunteer project. It is **not** affiliated with,
endorsed by, or a replacement for ASDMA, CWC, NESAC, IMD, SACHET, or any
government agency. It translates public data and may be incomplete, delayed, or
wrong. **In an emergency, follow official instructions and call ASDMA at 1070.**
