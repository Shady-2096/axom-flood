"""Tests for deriving reference flood levels from CWC hourly history.

Values are taken from the real cached series. The Goalpara case is the one that
matters most: three readings of 102.99 on a single April day in 2022, between
neighbours of 32.43 and 33.05, at a gauge whose all-time high is 37.43. It became
that year's "peak" and was marked usable for comparison sentences until guarded.
"""

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_spec = importlib.util.spec_from_file_location(
    "build_reference_floods",
    Path(__file__).resolve().parent.parent / "scripts" / "build_reference_floods.py",
)
brf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brf)

IST = ZoneInfo("Asia/Kolkata")


def _row(data_time: str, value: float, datatype: str = "HHS") -> dict:
    return {
        "id": {"dataTime": data_time, "datatypeCode": datatype, "stationCode": "002-MBDGHY"},
        "datatypeCode": datatype,
        "dataValue": value,
    }


def _monsoon_rows(year: int, level: float, hours: int) -> list[dict]:
    """`hours` hourly readings starting 1 June, all at `level`."""
    rows = []
    start = datetime(year, 6, 1, 0, tzinfo=IST)
    for offset in range(hours):
        moment = start.replace(tzinfo=None)
        moment = moment.fromordinal(moment.toordinal() + offset // 24).replace(
            hour=offset % 24
        )
        rows.append(_row(moment.isoformat(), level))
    return rows


def test_transcription_outlier_is_excluded_and_recorded() -> None:
    rows = _monsoon_rows(2022, 33.0, 2400) + [
        _row("2022-04-29T08:00:00", 102.99),
        _row("2022-04-29T13:00:00", 102.99),
        _row("2022-04-29T18:00:00", 102.99),
        _row("2022-07-15T10:00:00", 36.64),
    ]
    stats = brf._yearly_stats(rows, highest_flood_level=37.43)
    year = stats[2022]
    assert year["peak"] == 36.64, "the mistyped value must not become the peak"
    assert [item["level_m"] for item in year["discarded"]] == [102.99] * 3
    # Dropped values are listed, never silently removed.
    assert all("observed_at" in item for item in year["discarded"])


def test_a_genuine_record_flood_is_never_discarded() -> None:
    """The `above_hfl` state is the point of the product; records must survive."""
    rows = _monsoon_rows(2026, 94.0, 2400) + [_row("2026-07-15T10:00:00", 94.68)]
    stats = brf._yearly_stats(rows, highest_flood_level=94.35)
    assert stats[2026]["peak"] == 94.68
    assert stats[2026]["discarded"] == []


def test_no_ceiling_is_applied_without_a_published_hfl() -> None:
    rows = [_row("2024-07-01T10:00:00", 500.0)]
    stats = brf._yearly_stats(rows, highest_flood_level=None)
    assert stats[2024]["peak"] == 500.0
    assert stats[2024]["discarded"] == []


def test_foreign_datatypes_are_ignored() -> None:
    rows = [
        _row("2024-07-01T10:00:00", 34.0, "HHS"),
        # Gauge height above zero datum, not reduced level.
        _row("2024-07-01T10:00:00", 8.06, "HZS"),
        # Sensor battery voltage.
        _row("2024-07-01T11:00:00", 12.9, "BAT"),
    ]
    stats = brf._yearly_stats(rows, highest_flood_level=37.43)
    assert stats[2024]["readings"] == 1
    assert stats[2024]["peak"] == 34.0


def test_half_hour_rainfall_rows_are_ignored() -> None:
    rows = [
        _row("2024-07-01T10:00:00", 34.0),
        _row("2024-07-01T10:30:00", 0.0),
    ]
    stats = brf._yearly_stats(rows, highest_flood_level=37.43)
    assert stats[2024]["readings"] == 1


@pytest.mark.parametrize(
    ("coverage", "expected"),
    [(1.0, "high"), (0.75, "high"), (0.74, "partial"), (0.40, "partial"), (0.39, "sparse")],
)
def test_coverage_confidence_thresholds(coverage: float, expected: str) -> None:
    assert brf._confidence(coverage) == expected


def test_monsoon_coverage_is_measured_over_the_flood_season_only() -> None:
    """A year full of dry-season readings has seen none of the monsoon."""
    rows = [_row(f"2024-01-{day:02d}T10:00:00", 30.0) for day in range(1, 29)]
    stats = brf._yearly_stats(rows, highest_flood_level=37.43)
    assert stats[2024]["readings"] == 28
    assert stats[2024]["monsoon_readings"] == 0
    assert brf._confidence(0 / brf.MONSOON_HOURS) == "sparse"
