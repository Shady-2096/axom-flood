"""What the published rainfall artifact is allowed to say.

The pieces are tested on their own elsewhere. This is about the assembly: a
circle with a complete recent series gets a number for the windows it covers and
a refusal for the ones it does not, in the same file, at the same time. Getting
that wrong in either direction is the whole risk — one blank circle reads as no
rain, one confident 72-hour total built from six hours reads as a drought.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from axom_flood.rainfall.imerg import ImergRun, parse_imerg_observations
from axom_flood.rainfall.imerg_client import granule_for
from axom_flood.rainfall.subset import (
    GridBox,
    normalized_payload,
    parse_ascii_subset,
    payload_bytes,
    subset_request,
)

ROOT = Path(__file__).resolve().parents[1]

AS_OF = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)
NOW = AS_OF + timedelta(hours=14)
BOX = GridBox(west=91.3, south=26.4, east=91.5, north=26.6)

WET = "91.3000_26.4000"
DRY = "91.4000_26.4000"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_rainfall", ROOT / "scripts" / "build_rainfall.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zones_document() -> dict:
    """Two one-cell circles, so a share of 1.0 makes the arithmetic checkable."""

    def circle(locality_id: str, name: str, cell: str, longitude: float) -> dict:
        return {
            "locality_id": locality_id,
            "cell_degrees": 0.1,
            "circle_area_sq_km": 96.0,
            "boundary_sha256": "0" * 64,
            "cell_count": 1,
            "cells": [
                {
                    "grid_cell_id": cell,
                    "longitude": longitude,
                    "latitude": 26.45,
                    "share": 1.0,
                    "area_sq_km": 96.0,
                }
            ],
            "boundary": {
                "locality_id": locality_id,
                "revenue_circle": name,
                "district": "Baksa",
                "boundary_sha256": "0" * 64,
            },
        }

    return {
        "schema_version": 1,
        "cell_degrees": 0.1,
        "attribution": "© OpenStreetMap contributors",
        "provenance": {
            "boundary_review": "data/review/circle-boundaries/current.json",
            "boundary_sha256": "0" * 64,
        },
        "totals": {"circles": 2},
        "zones": [
            circle("test-wet", "Wet", WET, 91.35),
            circle("test-dry", "Dry", DRY, 91.45),
        ],
    }


def ascii_body(rate: float) -> str:
    return (
        "-----------------------------\n"
        f"Grid.precipitation[0][0], {rate}\n"
        "Grid.precipitation[0][1], 0.0\n"
        "Grid.lon, 91.35, 91.45\n"
        "Grid.lat, 26.45\n"
    )


def observations_for(hours: float, *, rate: float) -> list:
    """A continuous series of half hours ending exactly at `AS_OF`."""

    collected = []
    steps = int(hours * 2)
    for step in range(steps):
        start = AS_OF - timedelta(hours=hours) + timedelta(minutes=30 * step)
        granule = granule_for(start, run=ImergRun.LATE)
        request = subset_request(granule, BOX)
        parsed = parse_ascii_subset(ascii_body(rate), box=BOX)
        payload = normalized_payload(parsed, request=request)
        collected.extend(
            parse_imerg_observations(payload_bytes(payload), fetched_at=NOW)
        )
    return collected


@pytest.fixture(scope="module")
def script():
    return load_script()


def test_a_six_hour_series_answers_the_short_windows_and_refuses_the_long_ones(script):
    document = script.build_document(
        zones=zones_document(),
        zones_path=ROOT / "data" / "processed" / "rainfall-zones" / "test.json",
        observations=observations_for(6, rate=4.0),
        coverage={"granules_present": 12, "granules_expected": 144},
        run=ImergRun.LATE,
        as_of=AS_OF,
        now=NOW,
    )
    wet = next(row for row in document["circles"] if row["locality_id"] == "test-wet")

    # 4 mm/hour for six hours is 24 mm, and the one-hour window is 4 mm.
    assert wet["windows"]["6"] == pytest.approx(24.0)
    assert wet["windows"]["1"] == pytest.approx(4.0)
    # 24 and 72 hours reach past the start of the series and must stay empty.
    assert wet["windows"]["24"] is None
    assert wet["windows"]["72"] is None
    assert wet["window_unavailable_reasons"]["24"] == "window_not_covered"
    # The headline names the window it really used, not the one it wanted.
    assert wet["window_hours"] == 6
    assert "6 hours" in wet["headline"]


def test_a_circle_with_no_readings_says_so_rather_than_going_blank(script):
    zones = zones_document()
    document = script.build_document(
        zones=zones,
        zones_path=ROOT / "data" / "processed" / "rainfall-zones" / "test.json",
        # Only the wet circle's cell is in this series.
        observations=[
            observation
            for observation in observations_for(6, rate=4.0)
            if observation.grid_cell_id == WET
        ],
        coverage={},
        run=ImergRun.LATE,
        as_of=AS_OF,
        now=NOW,
    )
    dry = next(row for row in document["circles"] if row["locality_id"] == "test-dry")
    assert dry["status"] == "unavailable"
    assert dry["total_precipitation_mm"] is None
    assert "No satellite rainfall estimate is available" in dry["headline"]
    assert document["totals"]["unavailable"] == 1


def test_the_artifact_carries_the_estimate_and_the_hedge_once_each(script):
    document = script.build_document(
        zones=zones_document(),
        zones_path=ROOT / "data" / "processed" / "rainfall-zones" / "test.json",
        observations=observations_for(1, rate=0.0),
        coverage={},
        run=ImergRun.LATE,
        as_of=AS_OF,
        now=NOW,
    )
    shared = document["shared_text"]
    assert "satellite estimate" in shared["estimate_note"]
    assert "does not confirm flooding" in shared["hedge"]
    # No severity word may reach the artifact; IMD owns that vocabulary.
    body = json.dumps(document).casefold()
    for banned in ("very heavy", "extremely heavy", "warning issued"):
        assert banned not in body


def test_no_build_stamp_rides_inside_the_published_body(script):
    document = script.build_document(
        zones=zones_document(),
        zones_path=ROOT / "data" / "processed" / "rainfall-zones" / "test.json",
        observations=observations_for(1, rate=1.0),
        coverage={},
        run=ImergRun.LATE,
        as_of=AS_OF,
        now=NOW,
    )
    # Two identical rainfall states must hash to one artifact, or every rebuild
    # is a fresh download for every phone.
    assert "generated_at" not in document


def test_the_expected_window_end_lands_on_a_half_hour(script):
    as_of = script.latest_expected_as_of(
        ImergRun.LATE, datetime(2026, 8, 6, 23, 47, 31, tzinfo=UTC)
    )
    assert as_of.minute in {0, 30}
    assert as_of.second == 0
    assert as_of < datetime(2026, 8, 6, 23, 47, 31, tzinfo=UTC)


def test_the_subset_cache_is_keyed_on_the_cells_it_was_cut_down_to(script, tmp_path):
    """A cached subset holds only the cells asked for when it was fetched. When a
    circle is promoted to an analysis boundary its cells join the set, and a cache
    keyed on the granule alone would keep serving the narrower cut — no error, and
    the new circles silently publish nothing for any window reaching back past the
    granules downloaded since. It happened: 13 of 19 new circles came out with no
    24-hour and no 72-hour number."""

    narrow = {WET}
    wide = {WET, DRY}

    assert script.cells_digest(narrow) != script.cells_digest(wide)
    # Order and type of the set never move the name.
    assert script.cells_digest(wide) == script.cells_digest({DRY, WET})

    granule = "3B-HHR-L.MS.MRG.3IMERG.20260806-S050000-E052959.0300.V07C.HDF5"
    narrow_path = script.cached_subset_path(
        ImergRun.LATE, granule, script.cells_digest(narrow)
    )
    wide_path = script.cached_subset_path(
        ImergRun.LATE, granule, script.cells_digest(wide)
    )
    assert narrow_path != wide_path
    # Neither overwrites the other: the old cut stays readable under its own name.
    assert narrow_path.parent != wide_path.parent
    assert narrow_path.name == wide_path.name
