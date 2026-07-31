"""Derive per-gauge reference flood levels from cached CWC hourly history.

The implementation plan calls the reference flood table "manual, unglamorous, and
the single highest-value asset in the product", to be hand-built from historical
series and newspaper archives. CWC turns out to serve roughly seven years of its
own hourly history, so most of the table can be derived instead — but only if the
result is honest about how much of each year it actually saw.

The trap this script exists to avoid: coverage varies enormously by gauge and
year. Dibrugarh has 19,163 rows for 2019 and 5,626 for 2022. A yearly maximum
computed over 30% of the monsoon is not that year's flood peak, it is the peak of
what happened to be recorded. Publishing "higher than the 2022 flood" off that
would invent a landmark and mislead someone deciding whether to move.

So every year is emitted as an `observed_peak_m`, explicitly a LOWER BOUND on the
true peak, alongside the monsoon coverage it rests on, and only years that clear
a coverage floor are marked usable for comparison sentences. Unusable years are
kept — they are still evidence, and coverage can improve — but a consumer that
respects `is_usable_as_reference` can never quote a thin year at a user.

Usage:
    uv run python scripts/fetch_gauge_history.py --since 2019-01-01
    uv run python scripts/build_reference_floods.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from axom_flood.cwc.client import LEVEL_DATATYPE, FfsClient, parse_ffs_time
from axom_flood.cwc.pipeline import IST, _select_stations, is_plausible_level, load_district_lookup

# Assam's flood season. Peaks outside it are possible but a year is judged on how
# much of the monsoon was observed, since that is when a reference flood is set.
MONSOON_START_MONTH = 6
MONSOON_END_MONTH = 9
MONSOON_HOURS = (30 + 31 + 31 + 30) * 24  # June through September

# A year must have seen this much of the monsoon before its peak may be quoted to
# a user as "the YYYY flood". Chosen so a gauge that dropped out for a few days
# still counts, while one that recorded a third of the season cannot.
USABLE_MONSOON_COVERAGE = 0.75
PARTIAL_MONSOON_COVERAGE = 0.40

# Transcription errors survive the live path's shape checks because they are
# on-the-hour and positive. Goalpara's series holds three readings of 102.99 on a
# single April day in 2022, between neighbours of 32.43 and 33.05, against an
# all-time high of 37.43 — a mistyped 32.99, not a flood. Unfiltered it became
# that year's "peak" and was marked usable.
#
# The rule has to admit genuine record floods, which is the whole point of the
# `above_hfl` state, so it keys on physical impossibility rather than on being
# high: record floods beat the previous all-time high by tens of centimetres, not
# by tens of metres.
#
# This margin applies ONLY to deriving historical references. The live alerting
# path must never discard a reading for being large, and does not: see
# is_plausible_level, which keys on timestamp and sign alone. Every value dropped
# here is recorded in the output so the decision is auditable rather than silent.
MAX_METRES_ABOVE_HFL = 2.0


def _yearly_stats(
    rows: list[dict[str, Any]], *, highest_flood_level: float | None
) -> dict[int, dict[str, Any]]:
    ceiling = (
        highest_flood_level + MAX_METRES_ABOVE_HFL if highest_flood_level is not None else None
    )
    per_year: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "readings": 0,
            "monsoon_readings": 0,
            "peak": None,
            "peak_at": None,
            "discarded": [],
        }
    )
    for row in rows:
        if row.get("datatypeCode") != LEVEL_DATATYPE:
            continue
        value = row.get("dataValue")
        if value in (None, ""):
            continue
        observed_at = parse_ffs_time(row["id"]["dataTime"])
        level = float(value)
        if not is_plausible_level(observed_at, level):
            continue
        bucket = per_year[observed_at.year]
        if ceiling is not None and level > ceiling:
            bucket["discarded"].append(
                {"observed_at": observed_at.isoformat(), "level_m": level}
            )
            continue
        bucket["readings"] += 1
        if MONSOON_START_MONTH <= observed_at.month <= MONSOON_END_MONTH:
            bucket["monsoon_readings"] += 1
        if bucket["peak"] is None or level > bucket["peak"]:
            bucket["peak"] = level
            bucket["peak_at"] = observed_at.isoformat()
    return per_year


def _confidence(coverage: float) -> str:
    if coverage >= USABLE_MONSOON_COVERAGE:
        return "high"
    if coverage >= PARTIAL_MONSOON_COVERAGE:
        return "partial"
    return "sparse"


def build(*, data_dir: Path, now: datetime) -> dict[str, Any]:
    cache = data_dir / "cache" / "cwc-history"
    cached = sorted(cache.glob("*.json"))
    if not cached:
        raise SystemExit(
            f"no cached history in {cache}; run scripts/fetch_gauge_history.py first"
        )

    with FfsClient() as client:
        reference = client.fetch_reference(cache_dir=data_dir / "cache" / "cwc-reference")
    stations = _select_stations(
        reference,
        states=("Assam",),
        upstream_states=("Arunachal Pradesh",),
        district_lookup=load_district_lookup(),
    )

    gauges: dict[str, Any] = {}
    for path in cached:
        code = path.stem
        meta = stations.get(code)
        if meta is None:
            continue
        rows = json.loads(path.read_text())
        per_year = _yearly_stats(
            rows, highest_flood_level=meta["highest_flood_level_m"]
        )

        years = []
        for year in sorted(per_year):
            bucket = per_year[year]
            if bucket["peak"] is None:
                continue
            coverage = round(bucket["monsoon_readings"] / MONSOON_HOURS, 4)
            confidence = _confidence(coverage)
            is_partial_year = year == now.year
            years.append(
                {
                    "year": year,
                    # Deliberately not called "flood_peak": with partial coverage
                    # this is the highest level we saw, not the highest that occurred.
                    "observed_peak_m": bucket["peak"],
                    "observed_peak_at": bucket["peak_at"],
                    "readings": bucket["readings"],
                    "monsoon_readings": bucket["monsoon_readings"],
                    "monsoon_coverage": coverage,
                    "coverage_confidence": confidence,
                    "year_in_progress": is_partial_year,
                    # Physically impossible values excluded from this year's peak,
                    # listed rather than silently dropped.
                    "discarded_above_hfl_margin": bucket["discarded"],
                    # The only flag a consumer needs to respect. A year still in
                    # progress is never a historical reference.
                    "is_usable_as_reference": confidence == "high" and not is_partial_year,
                }
            )

        usable = [entry for entry in years if entry["is_usable_as_reference"]]
        gauges[code] = {
            "cwc_station_code": code,
            "gauge_id": meta["gauge_id"],
            "site_name": meta["site_name"],
            "river": meta["river"],
            "district": meta["district"],
            "warning_level_m": meta["warning_level_m"],
            "danger_level_m": meta["danger_level_m"],
            # CWC's own all-time high, which needs no derivation and outranks
            # anything in our seven-year window.
            "highest_flood_level_m": meta["highest_flood_level_m"],
            "highest_flood_level_date": meta["highest_flood_level_date"],
            "years": years,
            "usable_reference_years": [entry["year"] for entry in usable],
            "highest_usable_observed_peak_m": (
                max(entry["observed_peak_m"] for entry in usable) if usable else None
            ),
        }

    document = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source": "CWC FFS",
        "source_endpoint": "/iam/api/new-entry-data/specification/",
        "source_datatype": LEVEL_DATATYPE,
        "provenance": (
            "Derived from CWC's own hourly reduced-level history. Yearly figures are "
            "observed maxima over the readings CWC served, not independently verified "
            "flood peaks. A year is usable as a comparison reference only when at "
            f"least {USABLE_MONSOON_COVERAGE:.0%} of its June-September hours were "
            "observed and the year has ended."
        ),
        "usable_monsoon_coverage_threshold": USABLE_MONSOON_COVERAGE,
        "max_metres_above_hfl": MAX_METRES_ABOVE_HFL,
        "discarded_reading_count": sum(
            len(year["discarded_above_hfl_margin"])
            for gauge in gauges.values()
            for year in gauge["years"]
        ),
        "gauge_count": len(gauges),
        "gauges_with_any_usable_year": sum(
            1 for gauge in gauges.values() if gauge["usable_reference_years"]
        ),
        "gauges": gauges,
    }
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default="config/reference-floods.json")
    args = parser.parse_args()

    document = build(data_dir=Path(args.data_dir), now=datetime.now(IST))
    body = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(args.out).write_text(body)
    digest = hashlib.sha256(body.encode()).hexdigest()

    print(f"wrote {args.out} ({digest[:12]})")
    print(f"  gauges: {document['gauge_count']}")
    print(f"  gauges with at least one usable reference year: "
          f"{document['gauges_with_any_usable_year']}")
    for code, gauge in sorted(document["gauges"].items()):
        usable = gauge["usable_reference_years"]
        print(
            f"  {code:14} {gauge['site_name'][:20]:20} "
            f"usable years: {usable if usable else 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
