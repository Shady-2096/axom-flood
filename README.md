# Axom Flood

Axom Flood is a flood dashboard for Assam. It pulls together official river readings, government flood bulletins, and other public data, and presents them two ways: a short plain-language bulletin for anyone who just needs to know whether their area is at risk, and an interactive map for people who want to see the full picture.

Live at [assamflood.org](https://assamflood.org).

> Axom Flood translates and combines public data from agencies like CWC and ASDMA. It is not an official warning system and does not replace them. In an emergency, follow official instructions and call ASDMA at **1070**.

## Two ways to read it

Someone opening the site during a flood usually wants one answer: is the river near me rising, and how bad is it. So that is the first thing they get. Look up a place and you get a bulletin — the revenue circle, the river and gauge the reading comes from, the current level against the official warning and danger marks, which way it is moving, and how old the reading is. No hydrology, no interpretation:

> Kopili at Kampur is 56.55 m, below the official warning level, and rising about 0.5 cm every hour. No projection is shown beyond 12 hours.

For people who want more than a headline, the same data lives on a map you can actually work with. River levels are plotted for every gauge in the state, colour-coded from *below warning* through *danger* to *above the highest recorded flood*. On top of that sit the layers from the ASDMA situation report — affected people, affected villages, crop area, camp residents, relief centres, and damaged infrastructure — so you can see where the impact is concentrated, not just where the water is high. You can switch the base map between street and satellite, and read any single gauge on any single river. Open a gauge and you get the full readout: the current level against the warning, danger, and highest-recorded-flood marks, where it sits on that scale, the recent trend, and a link straight to the official CWC source it came from.

The map also carries the rest of the tools a resident might reach for: relief camps and their locations, emergency helplines, and a way to report conditions on the ground where they are.

## Detailed and data-saver modes

**Detailed mode** is the default and the main experience — the full map, satellite imagery, boundaries, and every layer. It is meant to be rich, and it has no data budget.

**Data-saver mode** is for a bad connection. It drops the map and the heavy layers completely and gives you only the bulletin for whichever place you look up: the same numbers, none of the network cost. On 2G during a flood, that is the difference between a page that loads and one that doesn't.

## Where the data comes from

Bringing several sources into one view — and being honest about the state of each — is most of what the project does.

| Source | Role | State |
|---|---|---|
| **CWC FFS** (`ffs.india-water.gov.in`) | Primary river levels, thresholds, and official forecasts | Live, refreshed every 2 hours |
| **ASDMA bulletins** | Official flood-impact reports (affected villages, camps, crop, infrastructure) | Live, but blocked from cloud hosts, so fetched on a schedule from a separate machine — expect occasional gaps |
| **OpenStreetMap** | Place names and district / revenue-circle boundaries the census lacks | Live (ODbL — attributed in shipped data) |
| **Census 2011** | Administrative unit names and membership | Static; reflects 2011 boundaries |
| **UDISE** | School locations, used to match relief camps | 2021 snapshot, labelled stale |
| **NWDP gauges** | Secondary gauge cross-check | Reachable but its last real reading is old; shown as *no data* |
| **SMART AXOM (water levels)** | Station-to-revenue-circle name crosswalk CWC does not expose | Live, but only a 1-hour-stale mirror of CWC's own levels, so used for names only |
| **SMART AXOM (alerts)** | Per-circle flood severity | Frozen since Aug 2023; shown as *no data*, never relied on |

More sources are on the way — Sentinel-1 radar, rainfall, and model forecasts among them. See [Where it's headed](#where-its-headed) for the plan. Several adapters already exist in the codebase but run on placeholder data until their real feeds and reviews are in place, and the README will say which is which until each one is live.

## How it's built

The repository is two halves that meet at a set of JSON files.

The **Python pipeline** (`src/axom_flood/`) has one adapter per source. Each one fetches, cleans, validates, and versions its data, then a build step writes content-hashed JSON bundles into `static/data/`. Raw payloads are addressed by their SHA-256 and never overwritten, and derived data keeps the source URL, a timestamp, and an extractor version attached, so fixing a parser never quietly rewrites history.

The **SvelteKit site** (`src/routes/`, `src/lib/`) reads those bundles and renders the bulletin, the map, camps, and helplines. A small mutable pointer (`current.json`) decides which bundle is live, so publishing new data updates the site without redeploying it.

The river feed keeps itself current without anyone watching. A Cloud Run job in Mumbai runs every two hours: it ingests the CWC feed, rebuilds the bundle, and pushes a commit, and that push triggers a deploy. The site is a PWA, so once it has been opened its shell works offline.

## Where it's headed

The aim is to answer three different questions without letting any of them borrow another's certainty:

1. What do the official instruments and reports say right now?
2. What conditions make flooding more likely here or upstream?
3. What are people actually seeing on the ground?

Today the site answers the first one well, through CWC gauges and ASDMA reports. Most of the work ahead is the other two, and the rule stays the same throughout: a model forecast is not an observation, rain is not proof of flooding, and a citizen report is not an official river status. Every new layer is labelled for exactly what it is.

Roughly in order:

- **Right river, right gauge.** Finish reviewing which river each revenue circle actually drains, so no place shows a confident level borrowed from a river that doesn't reach it — and where no gauge fits, say so plainly. This is the review task under [Contributing](#contributing).
- **Context where there's no gauge.** Recent rainfall (NASA IMERG) and a terrain-susceptibility picture (MERIT Hydro), so circles the gauge network doesn't serve still get something useful — marked clearly as estimates, not readings.
- **Flood extent from satellite.** Sentinel-1 radar to see standing water directly, independent of any gauge.
- **Community reports.** A way for people to report conditions where they are, starting on Telegram, kept visually and clearly separate from official data.
- **Forecasts and lead time.** Upstream gauges for travel-time warnings, and model forecasts (GloFAS, and Google's flood API once access clears) shown as probabilities with an issue time, never as a gauge-like number.

## Principles

A flood tool that is wrong is worse than none, so a few rules are load-bearing:

- Missing or stale data is shown as *no data*, never filled in with a guess or an interpolation. If a gauge goes quiet, the site says so.
- A gauge's status is decided by its own reading against the published thresholds, not by an upstream field that might be blank.
- A gauge vanishing from the feed is not an all-clear. Its last reading is kept, flagged as missing, and allowed to age into *no data* rather than being dropped.
- The output is never dressed up as an official warning. It translates official data; it doesn't issue warnings.
- Anything unreviewed is labelled as such — unreviewed gauge-to-circle mappings, unverified camp locations, and the draft Assamese copy, which currently falls back to reviewed English.

## Tech stack

- **Pipeline:** Python 3.11+, managed with [uv](https://docs.astral.sh/uv/), driven by an `axom-flood` CLI
- **Site:** [SvelteKit](https://kit.svelte.dev/) with `adapter-static`, built with Vite; ships as an installable PWA
- **Map:** [MapLibre GL](https://maplibre.org/) with PMTiles
- **Hosting:** Vercel for the site, a Google Cloud Run job for the two-hourly refresh

## Repository layout

```
src/axom_flood/   Python data pipelines, one folder per source
src/routes/       Site pages: river, camps, situation, report, emergency, settings
src/lib/          Components, map code, data loading
scripts/          Build scripts and CI checks
config/           Hand-maintained reference data (localities, gauge mappings, circle shapes)
data/             Raw and processed source data, append-only and hash-addressed
static/data/      The JSON bundles the site downloads
ops/cloudrun/     The job that refreshes gauges every 2 hours
docs/             Source provenance and contributor notes
```

## Running it locally

You'll need Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22+.

```bash
# Site
npm ci
npm run dev        # dev server
npm run build      # production build into build/

# Pipeline
uv sync --extra dev --locked
uv run axom-flood cwc --backfill-hours 12    # ingest the primary gauge feed
uv run python scripts/build_pwa_bundle.py    # rebuild the data bundle the site reads
```

Before pushing, run the full CI set — a lint break fails the run before any test does:

```bash
npm ci && npm run check && npm test && npm run build && npm run check:seo && npm run check:browser && node scripts/check_design_scale.mjs && uv run ruff check . && uv run pytest && uv run python scripts/check_pwa_budget.py
```

## Contributing

Contributions are welcome, and some of the most useful work isn't code.

**Reviewing the river maps.** The biggest open task is confirming which river each revenue circle actually drains — the link that decides which gauge speaks for a place. Some are still assigned by distance, which is wrong across Assam's braided rivers and hills. The questions are written for anyone who knows Assam's rivers, not for hydrologists: which river drains this circle, which river is this gauge on. If that's you, start with [`docs/gauge-topology-questions.md`](docs/gauge-topology-questions.md). Reviewers are credited for what they are — river knowledge is never written up as a hydrologist sign-off.

**Reviewing the Assamese copy.** The Assamese translation is drafted but unreviewed, so the site falls back to English. A fluent reviewer would unblock the language most of the audience actually reads.

**Code.** Keep the source URL and timestamp on anything derived from a source, never overwrite a raw payload (they're hash-addressed), and add a fixture test when you touch an extractor. Detailed mode has no size budget; only data-saver mode is constrained. Open an issue before starting anything substantial, and run the full CI set above.

## License and attribution

The code is licensed under the [GNU Affero General Public License v3.0](LICENSE). You're free to use, modify, and redistribute it, but running a modified version as a network service means making your source available to its users.

OpenStreetMap data is © OpenStreetMap contributors under the [ODbL](https://opendatacommons.org/licenses/odbl/), and shipped data carries visible attribution. CWC, ASDMA, Census, and UDISE data belong to their respective agencies; Axom Flood redistributes derived views with provenance attached and claims no ownership of the underlying data.

## Disclaimer

Axom Flood is an independent, volunteer project. It is not affiliated with or endorsed by ASDMA, CWC, NESAC, IMD, or any government agency, and it may be incomplete, delayed, or wrong. It is an information tool, not an emergency service. In an emergency, follow official instructions and call ASDMA at 1070.
