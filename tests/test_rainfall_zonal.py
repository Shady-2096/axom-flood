"""What the rainfall zonal join must get right, and what it must refuse.

The arithmetic here decides a number a person reads during a flood, so the tests
are about two things: that an area-weighted mean is actually area-weighted, and
that every way of producing a confident-looking wrong number is closed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from axom_flood.rainfall.provenance import SourceRevision
from axom_flood.rainfall.zonal import (
    BoundaryGradeError,
    CoverageError,
    ImergGridCellObservation,
    ImergRun,
    MeasuredBoundary,
    aggregate_over_circle,
    cell_weights,
    grid_cell_id,
    load_measured_boundaries,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data" / "review" / "circle-boundaries" / "current.json"

REVISION = SourceRevision.capture(
    b"{}",
    source_id="nasa-gpm-imerg",
    source_url="fixture://imerg",
    fetched_at=datetime(2026, 8, 2, tzinfo=UTC),
    media_type="application/json",
)


def square(west: float, south: float, east: float, north: float):
    return [(west, south), (east, south), (east, north), (west, north), (west, south)]


def boundary(rings, *, locality_id="test-circle", grade="zonal") -> MeasuredBoundary:
    return MeasuredBoundary(
        locality_id=locality_id,
        revenue_circle="Test",
        district="Test",
        rings=tuple(rings),
        grade=grade,
        agreement=0.95,
        independent_points=40,
        snapshot_sha256="0" * 64,
        osm_id="relation/1",
    )


def observation(cell_id, longitude, latitude, rate, *, hours=1, run=ImergRun.LATE):
    return ImergGridCellObservation(
        grid_cell_id=cell_id,
        longitude=longitude,
        latitude=latitude,
        interval_start=datetime(2026, 8, 2, 0, tzinfo=UTC),
        interval_end=datetime(2026, 8, 2, hours, tzinfo=UTC),
        precipitation_rate_mm_per_hour=Decimal(str(rate)),
        run=run,
        product_version="07",
        revision=REVISION,
    )


# --- weights -------------------------------------------------------------


def test_a_circle_filling_exactly_one_cell_gets_that_cell_alone():
    weights = cell_weights(boundary([square(91.0, 26.0, 91.1, 26.1)]), cell_degrees=0.1)
    assert len(weights.weights) == 1
    assert weights.weights[0].grid_cell_id == "91.0000_26.0000"
    assert weights.weights[0].share == pytest.approx(1.0)


def test_a_circle_split_evenly_across_two_cells_splits_the_weight_evenly():
    # Spans the full height of both cells, half the width of each.
    weights = cell_weights(boundary([square(91.05, 26.0, 91.15, 26.1)]), cell_degrees=0.1)
    shares = {weight.grid_cell_id: weight.share for weight in weights.weights}
    assert shares == pytest.approx({"91.0000_26.0000": 0.5, "91.1000_26.0000": 0.5})


def test_an_uneven_split_weights_by_the_area_actually_inside_each_cell():
    # Three quarters in the western cell, one quarter in the eastern.
    weights = cell_weights(boundary([square(91.025, 26.0, 91.125, 26.1)]), cell_degrees=0.1)
    shares = {weight.grid_cell_id: weight.share for weight in weights.weights}
    assert shares["91.0000_26.0000"] == pytest.approx(0.75)
    assert shares["91.1000_26.0000"] == pytest.approx(0.25)


def test_weights_always_sum_to_one():
    weights = cell_weights(boundary([square(90.93, 26.07, 91.28, 26.31)]), cell_degrees=0.1)
    assert sum(weight.share for weight in weights.weights) == pytest.approx(1.0)


def test_a_concave_circle_re_entering_a_cell_is_not_double_counted():
    """A U shape crosses one cell boundary twice. Clipping must still close."""
    u_shape = [
        (91.00, 26.00), (91.20, 26.00), (91.20, 26.20), (91.15, 26.20),
        (91.15, 26.05), (91.05, 26.05), (91.05, 26.20), (91.00, 26.20),
        (91.00, 26.00),
    ]
    weights = cell_weights(boundary([u_shape]), cell_degrees=0.1)
    assert sum(weight.share for weight in weights.weights) == pytest.approx(1.0)
    # The U encloses 0.025 deg², not the 0.04 of its bounding box. Compared as a
    # ratio against that box so the assertion tests the clipping, not the
    # projection.
    box = cell_weights(boundary([square(91.0, 26.0, 91.2, 26.2)]), cell_degrees=0.1)
    ratio = weights.circle_area_sq_km / box.circle_area_sq_km
    assert ratio == pytest.approx(0.625, rel=1e-3)


def test_cells_are_named_by_their_south_west_corner():
    assert grid_cell_id(91.04, 26.09, 0.1) == "91.0000_26.0000"
    assert grid_cell_id(91.0, 26.0, 0.1) == "91.0000_26.0000"


def test_a_circle_below_zonal_grade_is_refused_before_any_arithmetic():
    with pytest.raises(BoundaryGradeError, match="zonal grade"):
        cell_weights(boundary([square(91.0, 26.0, 91.1, 26.1)], grade="display"))


def test_a_measured_boundary_will_not_place_an_individual_point():
    with pytest.raises(BoundaryGradeError, match="individual point"):
        boundary([square(91.0, 26.0, 91.1, 26.1)]).refuse_individual_placement(
            "putting a citizen report in a circle"
        )


# --- aggregation ---------------------------------------------------------


def test_uniform_rain_over_every_cell_gives_that_rain_over_the_circle():
    weights = cell_weights(boundary([square(91.05, 26.0, 91.15, 26.1)]), cell_degrees=0.1)
    observations = [
        observation(weight.grid_cell_id, weight.longitude, weight.latitude, 6, hours=2)
        for weight in weights.weights
    ]
    result = aggregate_over_circle(weights, observations)
    assert result.total_mm == pytest.approx(Decimal(12))
    assert result.cell_count == 2


def test_rain_in_one_cell_is_diluted_by_the_share_that_cell_holds():
    """A storm over a quarter of the circle is not the circle's rainfall."""
    weights = cell_weights(boundary([square(91.025, 26.0, 91.125, 26.1)]), cell_degrees=0.1)
    observations = []
    for weight in weights.weights:
        rate = 100 if weight.grid_cell_id == "91.1000_26.0000" else 0
        observations.append(
            observation(weight.grid_cell_id, weight.longitude, weight.latitude, rate)
        )
    result = aggregate_over_circle(weights, observations)
    assert result.total_mm == pytest.approx(Decimal(25))  # 100 mm over a 0.25 share


def test_a_missing_cell_produces_no_number_at_all():
    weights = cell_weights(boundary([square(91.05, 26.0, 91.15, 26.1)]), cell_degrees=0.1)
    first = weights.weights[0]
    with pytest.raises(CoverageError, match="refusing a partial average"):
        aggregate_over_circle(
            weights,
            [observation(first.grid_cell_id, first.longitude, first.latitude, 5)],
        )


def test_a_cell_from_outside_the_circle_is_refused_rather_than_averaged_in():
    weights = cell_weights(boundary([square(91.0, 26.0, 91.1, 26.1)]), cell_degrees=0.1)
    observations = [
        observation(weights.weights[0].grid_cell_id, 91.05, 26.05, 5),
        observation("99.0000_26.0000", 99.05, 26.05, 500),
    ]
    with pytest.raises(CoverageError, match="outside its own boundary"):
        aggregate_over_circle(weights, observations)


def test_early_and_late_runs_are_never_averaged_together():
    weights = cell_weights(boundary([square(91.05, 26.0, 91.15, 26.1)]), cell_degrees=0.1)
    runs = [ImergRun.EARLY, ImergRun.LATE]
    observations = [
        observation(weight.grid_cell_id, weight.longitude, weight.latitude, 5, run=run)
        for weight, run in zip(weights.weights, runs, strict=True)
    ]
    with pytest.raises(CoverageError, match="different products"):
        aggregate_over_circle(weights, observations)


def test_cells_covering_different_windows_are_not_presented_as_one_total():
    weights = cell_weights(boundary([square(91.05, 26.0, 91.15, 26.1)]), cell_degrees=0.1)
    observations = [
        observation(weights.weights[0].grid_cell_id, 91.05, 26.05, 5, hours=1),
        observation(weights.weights[1].grid_cell_id, 91.15, 26.05, 5, hours=3),
    ]
    with pytest.raises(CoverageError, match="different time windows"):
        aggregate_over_circle(weights, observations)


def test_no_observations_is_a_refusal_and_never_zero_millimetres():
    weights = cell_weights(boundary([square(91.0, 26.0, 91.1, 26.1)]), cell_degrees=0.1)
    with pytest.raises(CoverageError):
        aggregate_over_circle(weights, [])


# --- the real boundaries -------------------------------------------------


def test_every_promoted_circle_produces_usable_weights():
    review = json.loads(REVIEW.read_text())
    boundaries = load_measured_boundaries(ROOT / review["passed_geojson"], REVIEW)
    assert len(boundaries) == review["totals"]["passed"]
    for measured in boundaries:
        assert measured.grade == "zonal"
        weights = cell_weights(measured)
        assert weights.weights
        assert sum(weight.share for weight in weights.weights) == pytest.approx(1.0)


def test_the_published_weights_carry_what_they_may_not_be_used_for():
    review = json.loads(REVIEW.read_text())
    measured = load_measured_boundaries(ROOT / review["passed_geojson"], REVIEW)[0]
    record = measured.as_dict()
    assert record["promoted_by"] == "measurement"
    assert "individual point" in record["forbids"]
