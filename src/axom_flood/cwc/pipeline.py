"""Assam river gauge snapshots from the CWC Flood Forecasting System.

This is the first source in the project that carries all four things Phase 1
needs at once: a current observed level with its observation time, the gauge's
own identity, the official Warning/Danger/Highest Flood levels, and CWC's
approved forecast. It therefore supersedes the NWDP CSV as the primary feed.

The honesty rules from the NWDP adapter are kept unchanged. A station whose
newest reading is older than the freshness limit reports `status: no_data` and a
null `level_m`; no gap is ever interpolated; and a trend is only published from a
continuous window. FFS carries retired duplicate station codes that still return
readings from 2022, so per-station freshness gating is load-bearing here, not a
formality.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..gauges.pipeline import compute_trend, station_id
from .client import LEVEL_DATATYPE, STATION_TYPES, FfsClient, parse_ffs_time

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "CWC FFS"
DISTRICT_REGISTRY = Path("config/assam-districts.json")

# FFS resolves a station only as far as a tahsil, which is not a revenue circle,
# so the circle a gauge warns for cannot be derived from FFS at all. ASDMA's own
# SMART AXOM dashboard publishes that mapping for the stations it carries; the
# snapshot is refreshed by scripts/fetch_smart_axom_roster.py. Absent or stale
# entries only cost a gauge its circle, never its reading.
SMART_AXOM_CROSSWALK = Path("config/smart-axom-gauge-circles.json")

# Assam's own gauges, plus the upstream states whose Brahmaputra-system gauges
# give Assam lead time. Upstream rows are labelled and never counted as Assam
# district readings.
DEFAULT_STATES = ("Assam",)
DEFAULT_UPSTREAM_STATES = ("Arunachal Pradesh",)


def gauge_id_for(station_code: str, name: str) -> str:
    """Stable id that survives FFS's duplicate station names.

    Several Assam sites appear twice under different divisional codes, one live
    and one retired, so the code has to be part of the identity.
    """
    return f"cwc_{station_id(name)}_{station_id(station_code)}"


def _index(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row[key]: row for row in rows if row.get(key) is not None}


def _fold(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.casefold())


def load_district_lookup(registry_path: Path | None = None) -> dict[str, tuple[str, str]]:
    """Map a source's district spelling to this project's canonical name and slug.

    CWC spells three Assam districts differently from the project registry
    ("Marigaon", "Sivsagar", and the pre-2024 "Karimganj" for Sribhumi). Phase 1
    joins gauge alerts to relief camps by district, so the spellings have to be
    reconciled against one registry rather than per source.
    """
    path = registry_path or DISTRICT_REGISTRY
    if not path.exists():
        return {}
    registry = json.loads(path.read_text())
    lookup: dict[str, tuple[str, str]] = {}
    for district in registry.get("districts", []):
        entry = (district["name"], district["slug"])
        for spelling in [district["name"], *district.get("source_aliases", [])]:
            lookup[_fold(spelling)] = entry
    return lookup


def load_revenue_circle_lookup(
    crosswalk_path: Path | None = None,
    locality_registry: Path | None = None,
) -> dict[str, tuple[str | None, str]]:
    """Map a CWC station code to its revenue circle, canonical name first.

    Returns `(canonical_name, source_spelling)`. The canonical name is None when
    SMART AXOM's spelling does not resolve against the locality registry, which
    is common and expected: several of its `rc_name` values are not circles at
    all but drainage descriptors like `River_brahmaputra`. The source spelling is
    always retained so a reviewer can see what the mapping was based on.
    """
    # `_fold_place` rather than this module's `_fold`: the alias table is keyed
    # with digits preserved, and `_fold` strips them, so folding here with the
    # local rule would miss every circle whose name carries a numeral.
    from ..asdma.parser import _fold_place, load_circle_aliases

    path = crosswalk_path or SMART_AXOM_CROSSWALK
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    aliases = (
        load_circle_aliases(locality_registry)
        if locality_registry is not None
        else load_circle_aliases()
    )
    # Already folded by `load_district_lookup`, so `_strip_district_suffix`
    # compares against them with this module's `_fold`.
    districts = set(load_district_lookup(None))
    lookup: dict[str, tuple[str | None, str]] = {}
    for station in document.get("stations", []):
        source = (station.get("revenue_circle_source_name") or "").strip()
        code = station.get("cwc_station_code")
        if not code or not source:
            continue
        canonical = aliases.get(_fold_place(source))
        if canonical is None:
            canonical = aliases.get(_fold_place(_strip_district_suffix(source, districts)))
        lookup[code] = (canonical, source)
    return lookup


def _strip_district_suffix(name: str, districts: set[str]) -> str:
    """Drop a trailing `_<district>` qualifier, as in `Nazira_sivasagar`.

    SMART AXOM disambiguates a few circle names by appending the district. The
    suffix is only removed when it actually names a district, so an ordinary
    circle whose name contains an underscore is left alone.
    """
    head, separator, tail = name.rpartition("_")
    if not separator or not head:
        return name
    return head if _fold(tail) in districts else name


def load_station_reference(
    data_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Every CWC station this project has ever recorded, keyed by station code.

    The reference snapshots are content-addressed, so a run that changes one
    threshold writes a whole new file rather than editing the old one. Merging
    them gives one lookup that survives a revision bump: a station's coordinates
    do not move between revisions, and a station that has dropped out of the
    newest reference is still the gauge some circle was mapped to.

    Offline by design. Callers that only need to know where a gauge *is* — the
    locality builder and the mapping audit — must not have to reach the network
    to find out.

    Two things decide the merge, and neither is the filesystem.

    The order is by filename. It used to be by modification time, which orders
    nothing at all on the fresh `git clone` every Cloud Run job starts from:
    checkout stamps all three snapshots at once. A timestamp inside the file
    would be the better key, but the body is what the content address hashes, so
    adding one would write a new snapshot on every run even when nothing changed.
    Sorted names are at least the same order everywhere.

    A known value is never replaced by a null. One of the three snapshots on disk
    is a 37-station partial fetch that knows no revenue circles at all, and a
    plain `dict.update` lets it erase what a 169-station snapshot recorded — 17
    circles, on two of the six possible orderings. Accumulating field by field
    makes the result the same whichever order they arrive in, for everything
    except a field two snapshots genuinely disagree about.

    There are two of those today: station 059-UBDDIB carries danger and warning
    levels 2.11 m apart between revisions. Nothing reads thresholds from here —
    every caller wants coordinates, name, river, district, state — and on those
    the three snapshots agree completely. Recorded because the day something does
    read them, first-one-wins is not a good enough answer.
    """
    directory = (data_dir or Path("data")) / "reference" / "cwc"
    if not directory.exists():
        return {}
    stations: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        snapshot = json.loads(path.read_text())
        for code, station in (snapshot.get("stations") or {}).items():
            known = stations.setdefault(code, {})
            for field, value in station.items():
                if value is not None or field not in known:
                    known[field] = value
    return stations


def haversine_km(
    first: tuple[float, float] | list[float],
    second: tuple[float, float] | list[float],
) -> float:
    """Great-circle distance in kilometres between two [longitude, latitude] points."""
    from math import asin, cos, radians, sin, sqrt

    longitude1, latitude1 = radians(first[0]), radians(first[1])
    longitude2, latitude2 = radians(second[0]), radians(second[1])
    inner = (
        sin((latitude2 - latitude1) / 2) ** 2
        + cos(latitude1) * cos(latitude2) * sin((longitude2 - longitude1) / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(inner))


def _resolve_place(
    station: dict[str, Any],
    tahsils: dict[Any, dict[str, Any]],
    districts: dict[Any, dict[str, Any]],
    states: dict[Any, str],
) -> tuple[str | None, str | None]:
    """Resolve district and state from CWC's own tahsil table.

    Preferred over any coordinate or name heuristic of ours: it is the agency's
    own administrative assignment for the gauge.
    """
    tahsil = tahsils.get(station.get("tahsilId"))
    if not tahsil:
        return None, None
    district = districts.get(tahsil.get("districtId"))
    if not district:
        return None, None
    return district.get("name"), states.get(district.get("stateCode"))


def is_plausible_level(observed_at: datetime, level: float) -> bool:
    """Last-resort shape check on a reading already restricted to `LEVEL_DATATYPE`.

    This is deliberately not the mechanism that keeps foreign series out of the
    level history: that is the datatype filter in `client.LEVEL_DATATYPE`, because
    several of the other series a station reports are indistinguishable from a
    level by magnitude. `HZS` in particular is gauge height above the station's
    zero datum, so at Guwahati it reads 8.06 against a `HHS` level of 48.04 and a
    danger level of 49.68 — a value this function would happily accept.

    What it still catches: rainfall rows reported on the half hour, which are
    usually 0.0, and any non-positive reduced level, which no gauge in this
    network can legitimately report.

    Both checks are structural rather than statistical. A reading is dropped for
    its timestamp or its sign, never for being high or for moving fast, so a
    genuine flood surge can never be filtered out here.
    """
    if level <= 0:
        return False
    return observed_at.minute == 0 and observed_at.second == 0


def _level_status(
    level: float,
    *,
    warning: float | None,
    danger: float | None,
    highest: float | None,
) -> str:
    if highest is not None and level >= highest:
        return "above_hfl"
    if danger is not None and level >= danger:
        return "above_danger"
    if warning is not None and level >= warning:
        return "warning"
    return "normal"


def _append_readings(path: Path, readings: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        existing = {
            json.loads(line)["observed_at"] for line in path.read_text().splitlines() if line
        }
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        for reading in sorted(readings, key=lambda item: item["observed_at"]):
            observed_at = reading["observed_at"].isoformat()
            if observed_at in existing:
                continue
            handle.write(json.dumps({**reading, "observed_at": observed_at}, sort_keys=True) + "\n")
            existing.add(observed_at)
            added += 1
    return added


def _stored_readings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    readings = [
        json.loads(line) for line in path.read_text().splitlines() if line
    ]
    for reading in readings:
        reading["observed_at"] = datetime.fromisoformat(reading["observed_at"])
    readings.sort(key=lambda item: item["observed_at"])
    return readings


def _select_stations(
    reference: dict[str, list[dict[str, Any]]],
    *,
    states: tuple[str, ...],
    upstream_states: tuple[str, ...],
    district_lookup: dict[str, tuple[str, str]],
    circle_lookup: dict[str, tuple[str | None, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    static_rows = _index(reference["flood_forecast_static"], "stationCode")
    layer = _index(reference["layer_station"], "stationCode")
    geo = _index(reference["layer_station_geo"], "stationCode")
    rivers = {row["localriverId"]: row.get("name") for row in reference["rivers"]}
    tahsils = _index(reference["tahsils"], "tahsilId")
    districts = _index(reference["districts"], "districtId")
    state_names = {row["stateCode"]: row.get("name") for row in reference["states"]}

    wanted = {name.casefold() for name in states}
    upstream = {name.casefold() for name in upstream_states}

    selected: dict[str, dict[str, Any]] = {}
    for code, static in static_rows.items():
        if static.get("type") not in STATION_TYPES:
            continue
        station = layer.get(code)
        location = geo.get(code)
        if not station or not location:
            continue
        district, state = _resolve_place(station, tahsils, districts, state_names)
        if state is None:
            continue
        folded = state.casefold()
        if folded not in wanted and folded not in upstream:
            continue
        latitude, longitude = location.get("lat"), location.get("lon")
        if latitude is None or longitude is None:
            continue
        source_district = (district or "").strip()
        canonical = district_lookup.get(_fold(source_district)) if source_district else None
        circle, circle_source = (circle_lookup or {}).get(code, (None, None))
        selected[code] = {
            "gauge_id": gauge_id_for(code, location.get("name") or code),
            "cwc_station_code": code,
            # `Level` sites carry a CWC forecast; `Base` sites are observation
            # only and often have no published thresholds. Kept on the record so
            # a consumer can tell why a gauge reports a level but no alert state.
            "station_type": static.get("type"),
            "site_name": (location.get("name") or code).strip(),
            # Canonical where the registry knows the district, so Phase 1 can join
            # gauges to relief camps; otherwise the source spelling, title-cased.
            "district": (canonical[0] if canonical else source_district.title()) or None,
            "district_slug": canonical[1] if canonical else None,
            "district_source_name": source_district or None,
            # From ASDMA's roster, not FFS: see SMART_AXOM_CROSSWALK. Canonical
            # only where the spelling resolves against the locality registry.
            "revenue_circle": circle,
            "revenue_circle_source_name": circle_source,
            "state": state,
            "is_upstream_of_assam": folded in upstream,
            "river": rivers.get(station.get("streamLocalriverId")),
            "coordinates": [float(longitude), float(latitude)],
            "agency": "Central Water Commission",
            "telemetric": bool(station.get("telemetric")),
            "station_operational": bool(station.get("stationOperational")),
            "warning_level_m": static.get("warningLevel"),
            "danger_level_m": static.get("dangerLevel"),
            "highest_flood_level_m": static.get("highestFlowLevel"),
            "highest_flood_level_date": static.get("highestFlowLevelDate"),
            "source_url": f"https://ffs.india-water.gov.in/#/station/{code}",
        }
    return selected


def _forecast_for(code: str, forecasts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in forecasts
        if row.get("stationCode") == code
        and row.get("datatypeCode") == "HHS"
        and not row.get("pendingOfApproval")
        and row.get("realValue") is not None
    ]
    if not candidates:
        return None
    latest = min(candidates, key=lambda row: row["id"]["forecastedDate"])
    return {
        "forecast_level_m": latest["realValue"],
        "forecast_for": parse_ffs_time(latest["id"]["forecastedDate"]).isoformat(),
        "issued_at": parse_ffs_time(latest["id"]["issuedDate"]).isoformat(),
        "trend_word": latest.get("trend"),
        "revised": bool(latest.get("revised")),
    }


def ingest_cwc_gauges(
    *,
    data_dir: Path,
    now: datetime | None = None,
    stale_after_hours: int = 6,
    states: tuple[str, ...] = DEFAULT_STATES,
    upstream_states: tuple[str, ...] = DEFAULT_UPSTREAM_STATES,
    backfill_hours: int = 0,
    district_registry: Path | None = None,
    circle_crosswalk: Path | None = None,
    reference_cache_ttl_hours: float = 24,
    client: FfsClient | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(IST)
    district_lookup = load_district_lookup(district_registry)
    circle_lookup = load_revenue_circle_lookup(circle_crosswalk)
    owned = client is None
    client = client or FfsClient()
    try:
        # data/cache/ is gitignored: this is a transport optimisation, never
        # published data. The committed provenance is the reference snapshot below.
        reference = client.fetch_reference(
            cache_dir=data_dir / "cache" / "cwc-reference",
            cache_ttl_hours=reference_cache_ttl_hours,
        )
        latest_levels = client.fetch_latest_levels()
        above_warning = client.fetch_above_warning()
        forecasts = client.fetch_forecasts(now=now)
        stations = _select_stations(
            reference,
            states=states,
            upstream_states=upstream_states,
            district_lookup=district_lookup,
            circle_lookup=circle_lookup,
        )
        series: dict[str, list[dict[str, Any]]] = {}
        if backfill_hours > 0:
            series = client.fetch_series_for(
                sorted(stations), since=now - timedelta(hours=backfill_hours)
            )
    finally:
        if owned:
            client.close()

    aggregate = {row["stationCode"]: row for row in latest_levels if row.get("stationCode")}
    warnings = {row["stationCode"]: row for row in above_warning if row.get("stationCode")}

    # An empty national warning list is indistinguishable from "no station in
    # India is above its warning level". That has been observed transiently from
    # a host that is otherwise serving readings normally, so it is treated as
    # unavailable rather than as an authoritative all-clear. Alert status is
    # always computed from the level against the published thresholds, never from
    # this list, so an outage here degrades context and not the alert itself.
    classification_available = bool(warnings)

    # The reference tables decide every threshold and label a snapshot carries, so
    # they get their own content-addressed revision. Only the fields this pipeline
    # actually reads are stored, for the selected stations: the full upstream
    # bodies are about 15 MB per run and re-committing them daily would bury the
    # repository without adding provenance that changes any output.
    reference_snapshot = {
        "note": (
            "Field projection of the CWC reference tables for the selected stations. "
            "Endpoints and the full field list are recorded in src/axom_flood/cwc/client.py."
        ),
        "stations": {code: stations[code] for code in sorted(stations)},
    }
    reference_bytes = (
        json.dumps(reference_snapshot, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode()
    reference_revision = hashlib.sha256(reference_bytes).hexdigest()
    reference_path = data_dir / "reference" / "cwc" / f"{reference_revision}.json"
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    if not reference_path.exists():
        reference_path.write_bytes(reference_bytes)

    # Every observation a snapshot or series row can cite has to be inside the
    # body this revision hashes, backfilled history included. Otherwise a stored
    # reading points at a revision that never contained it.
    raw = {
        "latest_levels": [aggregate[code] for code in sorted(stations) if code in aggregate],
        "above_warning": [warnings[code] for code in sorted(stations) if code in warnings],
        "forecasts": [row for row in forecasts if row.get("stationCode") in stations],
        "series": {code: series[code] for code in sorted(series) if series.get(code)},
        "reference_revision": reference_revision,
    }
    raw_bytes = (json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n").encode()
    source_revision = hashlib.sha256(raw_bytes).hexdigest()
    raw_path = data_dir / "raw" / "cwc" / f"{source_revision}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)

    snapshots: list[dict[str, Any]] = []
    readings_added = 0
    readings_rejected = 0
    stations_without_readings: list[str] = []

    for code, meta in sorted(stations.items()):
        row = aggregate.get(code)
        series_path = data_dir / "series" / "gauges" / f"{meta['gauge_id']}.jsonl"
        # Datatype is re-checked here even though the client already filters. A
        # gauge-height row admitted as a level is the worst failure this pipeline
        # can produce, and it must not depend on one layer getting it right.
        candidates = [
            (parse_ffs_time(entry["id"]["dataTime"]), float(entry["dataValue"]))
            for entry in series.get(code, [])
            if entry.get("dataValue") is not None
            and entry.get("datatypeCode") == LEVEL_DATATYPE
        ]
        # A station can drop out of the aggregate response entirely, which is
        # exactly what telemetry failure during a flood looks like. That must
        # become `no_data` against its last known reading, never a station that
        # quietly vanishes from the feed.
        if row and row.get("latestDataValue") is not None and row.get("latestDataTime"):
            candidates.append(
                (parse_ffs_time(row["latestDataTime"]), float(row["latestDataValue"]))
            )
        # Applied to the aggregate's newest reading as well as to backfilled
        # history, so a placeholder row can never become a published level.
        plausible = [pair for pair in candidates if is_plausible_level(*pair)]
        readings_rejected += len(candidates) - len(plausible)
        incoming = [
            {
                "schema_version": 1,
                "gauge_id": meta["gauge_id"],
                "observed_at": observed_at,
                "level_m": level,
                "source": SOURCE,
                "source_revision": source_revision,
            }
            for observed_at, level in plausible
        ]
        readings_added += _append_readings(series_path, incoming)

        history = _stored_readings(series_path)
        if not history:
            # No reading now and none ever stored: there is nothing to report on.
            stations_without_readings.append(code)
            continue
        latest = max(history, key=lambda item: item["observed_at"])
        age_hours = (now - latest["observed_at"]).total_seconds() / 3600
        is_current = age_hours <= stale_after_hours
        trend, gap_detected = compute_trend(history)
        cwc = warnings.get(code, {})

        snapshots.append(
            {
                "schema_version": 1,
                **meta,
                "observed_at": latest["observed_at"].isoformat(),
                "level_m": latest["level_m"] if is_current else None,
                "last_observed_level_m": latest["level_m"],
                "data_age_hours": round(age_hours, 2),
                "trend_cm_per_hr": trend if is_current else None,
                "trend_window_hrs": 4,
                "gap_detected_in_trend_window": gap_detected,
                "readings_in_local_series": len(history),
                "status": (
                    "no_data"
                    if not is_current
                    else _level_status(
                        latest["level_m"],
                        warning=meta["warning_level_m"],
                        danger=meta["danger_level_m"],
                        highest=meta["highest_flood_level_m"],
                    )
                ),
                "cwc_status": (
                    cwc.get("status") if is_current and classification_available else None
                ),
                "cwc_trend": (
                    cwc.get("trend") if is_current and classification_available else None
                ),
                "cwc_classification_available": classification_available,
                "forecast": _forecast_for(code, forecasts),
                # False means CWC stopped returning this station this run, so the
                # snapshot rests on stored history alone.
                "in_latest_source_response": code in aggregate,
                "source": SOURCE,
                "source_revision": source_revision,
                "reference_revision": reference_revision,
            }
        )

    snapshots.sort(key=lambda item: item["gauge_id"])
    current = [item for item in snapshots if item["status"] != "no_data"]
    document = {
        "schema_version": 1,
        "source": SOURCE,
        "source_base_url": "https://ffs.india-water.gov.in",
        "source_revision": source_revision,
        "reference_revision": reference_revision,
        "generated_at": now.isoformat(),
        "stale_after_hours": stale_after_hours,
        "states": list(states),
        "upstream_states": list(upstream_states),
        "cwc_classification_available": classification_available,
        "cwc_warning_list_size": len(warnings),
        # FFS half-hour placeholder rows, dropped before they can be published.
        "readings_rejected_implausible": readings_rejected,
        "source_warnings": (
            []
            if classification_available
            else [
                "CWC's station-water-level-above-warning list returned no rows. "
                "Treated as unavailable, not as an all-clear. Alert status below is "
                "computed from observed levels against published thresholds."
            ]
        ),
        "station_count": len(snapshots),
        "stations_current": len(current),
        "stations_with_no_data": len(snapshots) - len(current),
        "stations_without_any_reading": sorted(stations_without_readings),
        # Selected stations CWC did not return this run. They still appear in
        # `stations`, resting on stored history, and go stale into `no_data`
        # rather than disappearing.
        "stations_missing_from_latest_response": sorted(
            item["cwc_station_code"]
            for item in snapshots
            if not item["in_latest_source_response"]
        ),
        # A non-empty list means CWC used an Assam district spelling the registry
        # does not know, so those gauges cannot be joined to relief camps yet.
        "unmapped_district_names": sorted(
            {
                item["district_source_name"]
                for item in snapshots
                if not item["is_upstream_of_assam"]
                and item["district_slug"] is None
                and item["district_source_name"]
            }
        ),
        "stations_at_or_above_danger": sorted(
            item["gauge_id"] for item in current if item["status"] in {"above_danger", "above_hfl"}
        ),
        "stations_at_or_above_warning": sorted(
            item["gauge_id"] for item in current if item["status"] != "normal"
        ),
        "stations": snapshots,
    }

    output_dir = data_dir / "processed" / "cwc"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = hashlib.sha256(
        (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode()
    ).hexdigest()
    output_path = output_dir / f"{artifact_id}.json"
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    # Which of the committed snapshots is live, written down rather than left to
    # the filesystem. The bundle build used to take the newest modification time.
    # That is right whenever this ingest has just run, and wrong the moment it
    # has not: a fresh `git clone` -- what every Cloud Run job starts from --
    # stamps all 122 snapshots with the checkout time, so "newest" becomes
    # whichever hash readdir happens to return first.
    #
    # The daily job is where that bites. It records a failed CWC ingest and
    # carries on to build the bundle anyway, deliberately, so that one bad source
    # cannot hold up the others. Without this pointer that path could publish a
    # snapshot from ten days earlier as the current river bundle -- every reading
    # correctly stamped and correctly aged into "no data", and the whole state
    # dark during a flood.
    (output_dir / "current.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record": "cwc_snapshot_pointer",
                "revision_id": artifact_id,
                "snapshot_url": f"data/processed/cwc/{artifact_id}.json",
                "generated_at": document["generated_at"],
                "source_revision": document["source_revision"],
                "totals": {
                    "stations": document["station_count"],
                    "stations_current": document["stations_current"],
                    "stations_with_no_data": document["stations_with_no_data"],
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return {
        "artifact_id": artifact_id,
        "station_count": document["station_count"],
        "stations_current": document["stations_current"],
        "stations_with_no_data": document["stations_with_no_data"],
        "stations_at_or_above_warning": document["stations_at_or_above_warning"],
        "stations_at_or_above_danger": document["stations_at_or_above_danger"],
        "unmapped_district_names": document["unmapped_district_names"],
        "cwc_classification_available": classification_available,
        "source_warnings": document["source_warnings"],
        "readings_added": readings_added,
        "readings_rejected_implausible": readings_rejected,
        "stations_missing_from_latest_response": document[
            "stations_missing_from_latest_response"
        ],
        "json": str(output_path),
        "raw": str(raw_path),
        "reference": str(reference_path),
    }
