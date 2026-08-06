"""What the 1/3/6/24/72-hour rainfall totals must get right, and what they refuse.

Every test here is about the same failure: a number that looks fine and is too
low. A hole in the middle of a window, a window that quietly ends early, two
products averaged together — none of them look wrong on the page, and all of
them read lowest exactly when a storm sat in the part that went missing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from axom_flood.rainfall.provenance import SourceRevision
from axom_flood.rainfall.windows import (
    RAINFALL_WINDOW_HOURS,
    REASON_MISSING_CELLS,
    REASON_SERIES_BROKEN,
    REASON_WINDOW_NOT_COVERED,
    accumulate_windows,
)
from axom_flood.rainfall.zonal import (
    CoverageError,
    ImergGridCellObservation,
    ImergRun,
    MeasuredBoundary,
    cell_weights,
)

AS_OF = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

REVISION = SourceRevision.capture(
    b"{}",
    source_id="nasa-gpm-imerg",
    source_url="fixture://imerg",
    fetched_at=AS_OF,
    media_type="application/json",
)


def square(west: float, south: float, east: float, north: float):
    return [(west, south), (east, south), (east, north), (west, north), (west, south)]


def weights_for(rings, *, cell_degrees: float = 0.1):
    return cell_weights(
        MeasuredBoundary(
            locality_id="test-circle",
            revenue_circle="Test",
            district="Test",
            rings=tuple(rings),
            grade="zonal",
            agreement=0.95,
            independent_points=40,
            snapshot_sha256="0" * 64,
            osm_id="relation/1",
        ),
        cell_degrees=cell_degrees,
    )


def series(
    weights,
    *,
    hours: int,
    rate,
    as_of: datetime = AS_OF,
    run: ImergRun = ImergRun.LATE,
    skip: set[datetime] | None = None,
    cells: set[str] | None = None,
):
    """Half-hourly observations covering the `hours` before `as_of`.

    `rate` is either a number applied to every cell, or a mapping from cell id to
    that cell's rate.
    """

    skip = skip or set()
    observations = []
    for weight in weights.weights:
        if cells is not None and weight.grid_cell_id not in cells:
            continue
        cell_rate = rate[weight.grid_cell_id] if isinstance(rate, dict) else rate
        start = as_of - timedelta(hours=hours)
        while start < as_of:
            end = start + timedelta(minutes=30)
            if start not in skip:
                observations.append(
                    ImergGridCellObservation(
                        grid_cell_id=weight.grid_cell_id,
                        longitude=weight.longitude,
                        latitude=weight.latitude,
                        interval_start=start,
                        interval_end=end,
                        precipitation_rate_mm_per_hour=Decimal(str(cell_rate)),
                        run=run,
                        product_version="07",
                        revision=REVISION,
                    )
                )
            start = end
    return observations


ONE_CELL = [square(91.0, 26.0, 91.1, 26.1)]
TWO_CELLS = [square(91.05, 26.0, 91.15, 26.1)]


# --- the totals themselves ------------------------------------------------


def test_a_steady_rate_accumulates_by_the_length_of_each_window():
    weights = weights_for(ONE_CELL)
    result = accumulate_windows(
        weights, series(weights, hours=72, rate=2), as_of=AS_OF
    )
    for hours in RAINFALL_WINDOW_HOURS:
        assert result.window(hours).total_mm == pytest.approx(Decimal(2 * hours))


def test_every_requested_window_comes_back_shortest_first():
    weights = weights_for(ONE_CELL)
    result = accumulate_windows(
        weights, series(weights, hours=72, rate=1), as_of=AS_OF
    )
    assert [entry.hours for entry in result.windows] == list(RAINFALL_WINDOW_HOURS)


def test_rain_over_part_of_a_circle_is_diluted_by_that_part_s_share():
    """A storm over a quarter of the circle is not the circle's rainfall."""
    weights = weights_for([square(91.025, 26.0, 91.125, 26.1)])
    rates = {"91.0000_26.0000": 0, "91.1000_26.0000": 40}
    result = accumulate_windows(
        weights, series(weights, hours=6, rate=rates), as_of=AS_OF
    )
    # 40 mm/h for 6 h over a 0.25 share.
    assert result.window(6).total_mm == pytest.approx(Decimal(60))


def test_a_window_records_how_many_granules_it_was_built_from():
    weights = weights_for(TWO_CELLS)
    result = accumulate_windows(
        weights, series(weights, hours=3, rate=1), as_of=AS_OF
    )
    # Two cells, six half hours each.
    assert result.window(3).granule_count == 12
    assert result.window(3).cell_count == 2


# --- refusals -------------------------------------------------------------


def test_a_short_series_leaves_the_long_windows_unavailable_not_low():
    weights = weights_for(ONE_CELL)
    result = accumulate_windows(
        weights, series(weights, hours=6, rate=3), as_of=AS_OF
    )
    assert result.window(6).total_mm == pytest.approx(Decimal(18))
    for hours in (24, 72):
        entry = result.window(hours)
        assert entry.total_mm is None
        assert entry.unavailable_reason == REASON_WINDOW_NOT_COVERED


def test_a_long_window_failing_does_not_take_the_short_ones_with_it():
    weights = weights_for(ONE_CELL)
    result = accumulate_windows(
        weights, series(weights, hours=6, rate=3), as_of=AS_OF
    )
    assert result.longest_available_hours == 6
    assert [entry.hours for entry in result.windows if entry.available] == [1, 3, 6]


def test_a_hole_in_the_middle_of_a_window_is_a_refusal_not_a_smaller_total():
    weights = weights_for(ONE_CELL)
    missing = AS_OF - timedelta(hours=2)
    result = accumulate_windows(
        weights,
        series(weights, hours=6, rate=3, skip={missing}),
        as_of=AS_OF,
    )
    assert result.window(1).total_mm == pytest.approx(Decimal(3))
    assert result.window(3).unavailable_reason == REASON_SERIES_BROKEN
    assert "gap" in result.window(3).unavailable_detail


def test_a_series_that_stopped_early_does_not_relabel_an_older_total():
    """The last two hours never arrived. No window may claim to end now."""
    weights = weights_for(ONE_CELL)
    observations = series(weights, hours=24, rate=5, as_of=AS_OF - timedelta(hours=2))
    result = accumulate_windows(weights, observations, as_of=AS_OF)
    assert all(not entry.available for entry in result.windows)
    assert result.longest_available_hours is None
    assert result.window(24).unavailable_reason == REASON_WINDOW_NOT_COVERED


def test_a_cell_with_no_readings_leaves_the_circle_without_a_number():
    weights = weights_for(TWO_CELLS)
    only_one = {weights.weights[0].grid_cell_id}
    result = accumulate_windows(
        weights, series(weights, hours=6, rate=4, cells=only_one), as_of=AS_OF
    )
    entry = result.window(6)
    assert entry.total_mm is None
    assert entry.unavailable_reason == REASON_MISSING_CELLS
    assert weights.weights[1].grid_cell_id in entry.unavailable_detail


def test_early_and_late_runs_are_never_accumulated_into_one_series():
    weights = weights_for(ONE_CELL)
    mixed = series(weights, hours=1, rate=1, run=ImergRun.LATE) + series(
        weights, hours=1, rate=1, as_of=AS_OF - timedelta(hours=1), run=ImergRun.EARLY
    )
    with pytest.raises(CoverageError, match="different products"):
        accumulate_windows(weights, mixed, as_of=AS_OF)


def test_a_cell_from_outside_the_circle_is_refused_before_any_arithmetic():
    weights = weights_for(ONE_CELL)
    observations = series(weights, hours=1, rate=1)
    observations.append(
        ImergGridCellObservation(
            grid_cell_id="99.0000_26.0000",
            longitude=99.05,
            latitude=26.05,
            interval_start=AS_OF - timedelta(minutes=30),
            interval_end=AS_OF,
            precipitation_rate_mm_per_hour=Decimal("500"),
            run=ImergRun.LATE,
            product_version="07",
            revision=REVISION,
        )
    )
    with pytest.raises(CoverageError, match="outside its own boundary"):
        accumulate_windows(weights, observations, as_of=AS_OF)


def test_no_observations_is_a_refusal_and_never_zero_millimetres():
    weights = weights_for(ONE_CELL)
    with pytest.raises(CoverageError):
        accumulate_windows(weights, [], as_of=AS_OF)


def test_the_window_end_must_land_on_a_half_hour():
    weights = weights_for(ONE_CELL)
    observations = series(weights, hours=1, rate=1)
    with pytest.raises(ValueError, match="half hour"):
        accumulate_windows(
            weights, observations, as_of=AS_OF + timedelta(minutes=15)
        )


def test_a_naive_window_end_is_refused():
    weights = weights_for(ONE_CELL)
    observations = series(weights, hours=1, rate=1)
    with pytest.raises(ValueError, match="UTC offset"):
        accumulate_windows(weights, observations, as_of=AS_OF.replace(tzinfo=None))


# --- what travels with the number ----------------------------------------


def test_the_published_record_carries_what_it_may_not_be_used_for():
    weights = weights_for(ONE_CELL)
    record = accumulate_windows(
        weights, series(weights, hours=1, rate=1), as_of=AS_OF
    ).as_dict()
    assert record["aggregation"] == "area_weighted_mean_over_circle"
    assert "individual point" in record["forbids"]
    assert record["run"] == "late"
    assert record["boundary_sha256"] == "0" * 64


def test_an_unavailable_window_publishes_a_null_and_a_reason_never_a_zero():
    weights = weights_for(ONE_CELL)
    record = accumulate_windows(
        weights, series(weights, hours=1, rate=9), as_of=AS_OF
    ).as_dict()
    long_window = next(entry for entry in record["windows"] if entry["hours"] == 72)
    assert long_window["available"] is False
    assert long_window["total_precipitation_mm"] is None
    assert long_window["unavailable_reason"] == REASON_WINDOW_NOT_COVERED


def test_every_source_revision_behind_a_total_travels_with_it():
    weights = weights_for(TWO_CELLS)
    entry = accumulate_windows(
        weights, series(weights, hours=1, rate=1), as_of=AS_OF
    ).window(1)
    assert entry.source_revision_sha256s == (REVISION.sha256,)
