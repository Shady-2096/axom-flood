# Data-source investigation and provenance

Last verified: 2026-07-29 (Asia/Kolkata).

## ASDMA flood bulletins

- Landing page: `https://asdma.assam.gov.in/resource/assam-flood-report`
- DRIMS application: `https://sdrf.assam.gov.in/dfr/`
- Download form: `https://sdrf.assam.gov.in/dfr/download?type=flood`

DRIMS requires a session and CSRF token. The client loads the form, posts the
requested date, and validates that the response is a PDF. An unpublished date
returns HTML containing `PDF Not Found`. The 2026-07-25 bulletin was retrieved
and parsed on 2026-07-26.

Extractor v3 preserves the bracketed revenue-circle detail that v2 discarded:
affected villages, population, crop area, camps, distribution centres, camp
occupants, and confirmed deaths. The real 2026-07-26 bulletin produced five
circle records for the Sivasagar row, including Nazira's population `17,885`
and crop area `8,551` hectares. Circle spellings resolve through
`config/assam-localities.json`; each record retains its source spellings.
Extractor-v2 artifacts are never overwritten, and v3 adds a separate
`*-extractor-v3-circles.csv`.

Extractor v5 removes the remaining dependence on fixed physical PDF columns.
It finds district rows and standalone numeric values semantically, verifies
population totals against demographic and revenue-circle detail, resolves camp
and distribution-centre columns through their bracket grammar, and joins
population detail split across a page boundary. Complete state, district, and
circle hierarchies are reconciled before extraction succeeds. The retained
2026-07-25, 2026-07-26, and 2026-07-27 PDFs all pass v5; earlier extractor
artifacts remain immutable.

Extractor v7 adds the full Phase B impact contract: missing people; livestock
affected and washed away; house damage; rescue and evacuation; quantified
relief materials and source-text notes; and detailed road, bridge, breached
embankment, and affected embankment records. Every aggregate field and
infrastructure record carries page/table/row provenance, completed with the
immutable source revision SHA during persistence. Coordinate points publish
only inside a broad Assam envelope; otherwise the record retains source
coordinate text and falls back to revenue-circle, district, or unresolved
scope.

The retained 2026-07-26 report declares 105 damaged roads but contains 97
extractable non-`Nil` detail rows. Extractor v7 preserves the official count,
the 97 records, and a structured mismatch warning. It does not invent the
missing records or silently replace the source aggregate. Extractor v6 is
retained as a superseded intermediate artifact after schema validation caught
an incorrectly named continuation field; v7 is the first Phase B artifact that
passes the versioned bulletin schema.

Validator v1 independently rechecks the versioned schema, source identity,
required fields, non-negative values, component and district arithmetic,
field-level provenance, report/fetch chronology, infrastructure totals, and
coordinate/match-scope safety. Validation evidence and normalized impact
snapshots are immutable and content-revision addressed. The mutable
`impact-current.json` pointer is replaced only after both internal and public
artifacts exist; a failed or older candidate cannot regress it.
The mutable `impact-history.json` index lists every publishable immutable
revision for same-date disclosure and report-to-report comparison. It never
turns a historical or superseded revision into the current report.

Publication states are explicit:

- `validated` exposes the complete impact-v1 profile;
- `validated_partial` exposes only a named allow-list;
- `historical` and `superseded` retain valid evidence without moving the
  current pointer; and
- `quarantined` records failures while preserving the prior pointer.

The 2026-07-26 infrastructure mismatch is the sole approved partial exception:
the official count of 105 damaged roads is retained, but the 97 incomplete road
records are excluded. Unknown warnings quarantine instead of silently reducing
the profile. Parser/layout drift preserves the downloaded raw PDF before
writing quarantine evidence.

GitHub-hosted attempts timed out at the earlier 60-second limit even though the
same flow works locally. The client now allows 180 seconds per request, logs
the form GET and PDF POST separately with durations, and repeats the complete
CSRF flow up to three times for transport failures and transient HTTP statuses.
Contract-invalid responses and unpublished dates still fail immediately.

Hosted run `30219121423` exercised the hardened path. All three attempts failed
during the form GET with `ConnectTimeout` after roughly 133–135 seconds; none
reached the PDF POST. The correct operational fallback is therefore a trusted
runner with a reachable network path, preferably hosted in India, rather than
a still-longer GitHub-hosted timeout.

## District relief-camp lists

All 35 configured district sites are crawled. There is no uniform URL scheme,
so the discovery output records candidates, failures, and districts with no
candidate. Verified document families include Chirang's dedicated 2026 camp
PDF and large district contingency plans such as Sivasagar's.

The first complete crawl downloaded 19 source documents from 10 districts and
extracted 150 raw rows. Coordinates were present for 44 rows. The other rows
and contingency-plan extractions are preserved in review queues rather than
silently promoted to verified camp locations.

## UDISE+

- Official system: `https://udiseplus.gov.in/`
- Reproducible community mirror: `https://github.com/datameet/udise_schools`

The official portal documents GIS coordinates but no unauthenticated bulk
export was identified. Phase 0 therefore uses a content-hashed 2021 community
snapshot to exercise the full ingest and matcher. It contains 62,393 Assam
schools with coordinates. This snapshot is explicitly stale and must not be
used for operational navigation without an official refresh.

Matches are district-blocked, normalized, ambiguity checked, and labelled
`high`, `medium`, or `unverified`. Medium and unverified records go to human
review.

## Census 2011 locality directory

- Catalog: `https://censusindia.gov.in/nada/index.php/catalog/7057`
- Assam MDDS workbook:
  `https://censusindia.gov.in/nada/index.php/catalog/7057/download/10169/Rdir_2001_MDDS_18.xls`
- Producer: Office of the Registrar General & Census Commissioner, India.

Phase 1 uses the official rural MDDS directory for district, sub-district
(revenue-circle), village names, and stable Census codes. The exact source
SHA-256 is embedded in both generated config artifacts. This is an
administrative-vintage limitation: the registry reflects 2011 boundaries and
does not pretend to be a current LGD export.

The Census workbook has no village coordinates. Centre points are derived from
the already-recorded UDISE coordinate snapshot: an exact district-and-village
name match uses the median school coordinate; the remainder use that revenue
circle's median exact-match point and are labelled
`revenue_circle_fallback`. These points support search and display only. They
are never used to choose a gauge.

Every primary gauge assignment is made by river and upstream/downstream
position in `scripts/build_localities.py`. The output records the basis and
confidence. Medium and unverified assignments are written to
`data/review/locality-gauge-mappings/current.json`; there is no
nearest-gauge-by-distance fallback.

The LGD download directory was evaluated but returned `EntityManagerFactory is
closed` on 2026-07-27, so no LGD data was incorporated and no LGD freshness is
claimed.

## River gauges

The primary feed is now CWC FFS. NWDP is retained only as a secondary
cross-check. See [`config/gauge-sources.json`](../config/gauge-sources.json).

### CWC Flood Forecasting System (primary)

- Site: `https://ffs.india-water.gov.in/`

The earlier conclusion that FFS exposed no usable current-reading contract was
wrong. The site is an Angular application that reads unauthenticated JSON
endpoints, and those endpoints carry everything Phase 1 needs. There is no
published documentation for them, so the exact paths, the `specification` filter
DSL, and each field depended on are recorded in
[`src/axom_flood/cwc/client.py`](../src/axom_flood/cwc/client.py).

| Endpoint | Supplies |
| --- | --- |
| `/iam/api/flood-forecast-static/specification/` | Warning Level, Danger Level, Highest Flood Level and its date |
| `/iam/api/layer-station/specification/` | River id, tahsil, telemetry and operational flags |
| `/iam/api/layer-station-geo/specification/` | Station name and coordinates |
| `/iam/api/new-entry-data-aggregate/specification/` | Newest observed level and its observation time |
| `/iam/api/new-entry-data/specification/` | Hourly observation history for trend |
| `/iam/api/new-forecasted-entry-data/specification/` | Approved official forecasts with issue time |
| `/ffm/api/station-water-level-above-warning/` | CWC's own warning/danger classification and trend |
| `/iam/api/master-tahsil/`, `/iam/api/layer-district/`, `/iam/api/layer-state/` | District and state, from the agency's own tables |
| `/iam/api/master-basin-localriver/` | River names |

The station-class filter was widened on 2026-07-30 from `Level`/`Inflow` to
include `Base`. FFS labels a forecast site `Level`, a reservoir `Inflow`, and a
plain observation site `Base`; the earlier filter assumed a `Base` site carried
no thresholds. Comparing against ASDMA's own roster (below) disproved that: of
the 70 Assam gauges ASDMA publishes, 46 are `Base` and 13 of those have a
published danger level. Widening the filter took the roster from 37 stations to
157 (120 Assam, 37 Arunachal), covering 69 of ASDMA's 70. The one exception,
Chotabekra on the Barak, is placed in Manipur by FFS's own tahsil table and so
falls outside the configured states.

Three alternatives cannot be expressed as two `or` clauses in the specification
DSL, because a clause object keys them as `where`/`and`/`or`. The `in` operator
takes them as one comma-joined string; a JSON list is rejected with 400.

Verified live on 2026-07-27 (15:20 IST): 30 Assam-region Level gauges reporting
within six hours, the newest readings at the current hour. Covered rivers
include the Brahmaputra (Dibrugarh, Neamatighat, Tezpur, Guwahati, Goalpara,
Dhubri), Barak, Kushiyara, Katakhal, Kopili, Dhansiri, Subansiri, Manas, Beki,
Pagladiya, Puthimari, Sankosh, Jiabharali, Ranganadi, Buridehing, Desang and
Dikhow.

District and state come from CWC's own tahsil table rather than from any
coordinate or name heuristic of ours, so a gauge is only labelled with an Assam
district when the agency assigns it one. Gauges in Arunachal Pradesh on the
Brahmaputra system are kept for upstream lead time and flagged
`is_upstream_of_assam`; they are never counted as Assam district readings.
Gauges in other neighbouring states are excluded outright.

Known source-side defects, both handled rather than worked around:

- FFS still serves retired duplicate station codes whose newest reading is from
  2022, next to the live code for the same site. Per-station freshness gating is
  therefore load-bearing, and `gauge_id` includes the station code so the live
  and retired records cannot merge.
- `new-forecasted-entry-data` answers HTTP 500 with a
  `JpaObjectRetrievalFailureException` when the `forecastedDate` threshold
  reaches back far enough to include forecasts whose aggregate row was deleted.
  The public site only queries forward from the current instant; the adapter
  does the same and treats forecasts as best-effort.
- A timestamp without milliseconds is rejected with HTTP 500.
- **`new-entry-data` returns several different series per station and hour, and
  some are indistinguishable from a water level by magnitude.** Observed
  datatypes: `HHS` reduced level in metres above mean sea level, which is the
  only one comparable to the published thresholds; `HZS` and `HZF` gauge height
  above the station's zero datum; `HHT` a second level series offset by about a
  metre; `MPM` and `MPS` rainfall, reported on the half hour and usually `0.0`;
  `BAT` sensor battery voltage; `FIN` reservoir inflow.

  `HZS` is the dangerous one. At Guwahati it reads `8.06` where `HHS` is `48.04`
  against a danger level of `49.68`, so storing it as a level would report a
  river forty metres below danger while it sat just under it. In a 12-hour
  backfill across 37 stations, 12 stations returned on-the-hour positive `HZS` or
  `HZF` rows at the same timestamps as their `HHS` rows.

  Rows are therefore filtered by datatype, in this process rather than in the
  query, because the specification DSL's three-clause nesting is undocumented and
  a filter that silently failed would admit gauge heights as levels. A
  timestamp-and-sign shape check in `is_plausible_level` backs it up and catches
  the half-hour rainfall rows, but it is explicitly not the mechanism that keeps
  foreign series out: it would accept `HZS` without complaint. Rejections are
  counted in `readings_rejected_implausible`. Neither check keys on magnitude or
  rate of change, so a genuine flood surge cannot be filtered out.

  An earlier revision of this document described these as "half-hour placeholder
  rows", most of them `0.0`. That was the visible symptom of the rainfall series
  only, and it missed the on-the-hour gauge-height rows entirely.
- An unfiltered bulk query over `new-entry-data` does not return within four
  minutes, so history is backfilled per station with bounded concurrency.
- A station can disappear from the latest-reading response altogether, which is
  indistinguishable from telemetry failure during a flood. The adapter keeps such
  a station in the feed against its stored history, flags
  `in_latest_source_response: false`, and lets it age into `no_data`. Dropping it
  would read as a gauge that is fine.
- A full reference-table fetch is roughly 15 MB and has taken about 170 seconds.
  The tables are cached under gitignored `data/cache/` for 24 hours, which is
  bounded deliberately because Danger Level values can legitimately change.
  Committed provenance is a separate field-projection snapshot under
  `data/reference/cwc/`, referenced by `reference_revision`.
- Individual endpoints intermittently time out, and the national warning list was
  once served empty by an otherwise healthy host. An empty warning list is
  indistinguishable from "no station in India is above warning", so it is
  recorded as unavailable through `cwc_classification_available` and never
  treated as an all-clear. Alert status is always computed from the observed
  level against the published thresholds, so this degrades context only.
  Transport failures and 5xx are retried up to three times with linear backoff;
  4xx and malformed bodies surface immediately.

The freshness and trend rules from the NWDP adapter are unchanged: a station
past the six-hour limit reports `status: no_data` with a null `level_m`, no gap
is interpolated, and a trend is published only from a continuous four-hour
window with no interval above 90 minutes. CWC's own status and trend words are
also withheld for a stale gauge.

### NWDP Assam hourly dataset (secondary)

- Dataset: `https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-assam-department`

The resource's file modification date advances — it read 2026-07-26 on
2026-07-27 — but the measurements inside it do not. The verified CSV contains
330 rows for a single Darrang station, carries no river name, and its newest
observation is 2026-05-30 at 23:00. The API returns the same 330 stale records.
The adapter stores each observation and emits `no_data` with a null current
level. This source cannot carry Phase 1 alerts.

## SMART AXOM and FLEWS

- SMART AXOM dashboard: `https://apps.nesdr.gov.in/asdma/`
- ASDMA web-service listing:
  `https://asdma.assam.gov.in/information-services/web-portal-web-services`
- NESAC FLEWS programme:
  `https://nesac.gov.in/scientific-programmes/disaster-management-support/`

The original plan's claim that no citizen-facing official channel exists is
outdated: SMART AXOM is now an official public dashboard and mobile app. Its
dashboard calls public category endpoints under
`https://api.nesdr.gov.in/asdma/`, which the Phase 0 adapter preserves and
normalizes.

The endpoint's own last-update value is `2023-08-26 09:41:00`. Consequently the
adapter emits `status: no_data` and never presents its 108 returned rows as
current alerts. A documented current feed would have to come from NESAC/ASDMA.
The product positioning follows from this: Axom Flood should complement SMART
AXOM with interpretation, shelter matching, offline access, and source
aggregation.

### SMART AXOM water-level roster (reference only)

- Page: `https://smartaxom.nesdr.gov.in/analytics/flood/waterlevelinfo`
- Endpoint: `POST https://smartaxom.nesdr.gov.in/api_v2/dataCWC`

Distinct from the frozen category endpoints above, this one is live and updates
hourly. It is **not** used as a data source. Checked on 2026-07-30, all 70
stations it publishes are already in CWC FFS, values agree to the centimetre,
and FFS was an hour fresher (12:00 against 11:00). It is a downstream mirror.

What it adds is editorial, and is captured as a snapshot in
[`config/smart-axom-gauge-circles.json`](../config/smart-axom-gauge-circles.json)
by [`scripts/fetch_smart_axom_roster.py`](../scripts/fetch_smart_axom_roster.py):

- the subset of FFS stations ASDMA itself treats as Assam-relevant, which is
  what exposed the `Base` gap above;
- `rc_name`, the revenue circle a gauge warns for. FFS resolves a station only
  as far as a tahsil, so the circle cannot be derived from FFS at all.

53 of the 70 circle spellings resolve against
[`config/assam-localities.json`](../config/assam-localities.json). Of the rest,
five are not circles (`River_brahmaputra`, `District_dima-hasao` and similar)
and seven are real circles absent from the registry: Barnagar, Bijni, Dhubri,
Golokganj, Goreswar, Kokrajhar, Manikpur. An unresolved spelling leaves
`revenue_circle` null and retains the source spelling; it is never guessed.

The endpoint authenticates with a fixed identifier encrypted under an AES key
hardcoded in the site's own JavaScript. Both constants ship to every visitor, so
this is obfuscation rather than a credential. Its TLS chain repeats an
intermediate and routes up through a root certifi no longer carries, so the
fetch script verifies against the OS trust store via `truststore`; verification
is never disabled.

## NASA GPM IMERG (rainfall)

Half-hourly satellite rainfall estimates, used for circles the gauge network does
not serve. Two runs matter: **Early**, which NASA attributes roughly four-hour
availability to, and **Late**, which is the better estimate and arrives later.

An earlier handoff to this project claimed the four-hour figure for Late. It is
wrong, and the correction is not a better constant — it is to stop relying on a
constant. `ImergDownload.observed_latency_hours` is measured from the archive's
own publication time on every download. `IMERG_POLICIES[...].typical_latency_hours`
is kept only as an expectation to compare a measurement against.

**Access:** Earthdata Login, free registration, operator-supplied token. A valid
token is not sufficient on its own — GES DISC must also be authorised once under
Earthdata → Applications → Authorized Apps. A 403 with a working token almost
always means that step was missed.

⚠️ **Unverified as of 2026-08-02.** No Earthdata account exists yet, so every
IMERG test runs against synthetic bytes. Those tests prove the refusals, the
granule arithmetic, and that latency is measured rather than assumed. They do
**not** prove the archive path, the `V07B` version suffix, or the token flow.

```
uv run python scripts/smoke_imerg.py --dry-run   # prints the URL, no account needed
uv run python scripts/smoke_imerg.py             # the actual proof, needs EARTHDATA_TOKEN
```

Until that second command has passed once, granule URLs are a documented
convention and not a confirmed fact. The zonal weights in
`data/processed/rainfall-zones/` do not depend on any of this — they are geometry
and were built without an account.

## Google Flood Forecasting API

Google documents the API as free, CC BY 4.0, and pilot/waitlist access.
Submission requires the operator's Google identity and project details; no application is
represented as submitted until those are supplied.
