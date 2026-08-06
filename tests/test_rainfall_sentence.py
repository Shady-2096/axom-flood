"""What the rainfall copy may and may not say to a person on a phone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from axom_flood.rainfall.imerg import ImergRun
from axom_flood.rainfall.sentence import describe_circle_rainfall
from axom_flood.rainfall.windows import (
    REASON_MISSING_CELLS,
    REASON_WINDOW_NOT_COVERED,
    CircleRainfall,
    WindowTotal,
)

AS_OF = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
NOW = AS_OF + timedelta(hours=2)


def window(hours: int, total_mm=None, reason=None) -> WindowTotal:
    return WindowTotal(
        hours=hours,
        interval_start=AS_OF - timedelta(hours=hours),
        interval_end=AS_OF,
        total_mm=None if total_mm is None else Decimal(str(total_mm)),
        unavailable_reason=reason,
        unavailable_detail=None if reason is None else "detail",
        cell_count=4,
        granule_count=0 if total_mm is None else hours * 2 * 4,
        source_revision_sha256s=(),
    )


def rainfall(*windows, run=ImergRun.LATE, as_of=AS_OF) -> CircleRainfall:
    return CircleRainfall(
        locality_id="barama",
        run=run,
        as_of=as_of,
        boundary_sha256="0" * 64,
        cell_count=4,
        windows=windows,
    )


def describe(record, *, now=NOW, place="Barama circle", preferred_hours=24):
    return describe_circle_rainfall(
        record, now=now, place_name=place, preferred_hours=preferred_hours
    )


# --- what it says when there is a number ---------------------------------


def test_the_headline_leads_with_the_last_24_hours():
    result = describe(rainfall(window(3, 12), window(24, 72)))
    assert result["status"] == "estimate"
    assert result["window_hours"] == 24
    assert "about 72 mm" in result["headline"]
    assert "the last 24 hours" in result["headline"]
    assert "Barama circle" in result["headline"]


def test_every_sentence_says_it_is_an_estimate_and_not_proof_of_flooding():
    result = describe(rainfall(window(24, 40)))
    assert "satellite estimate, not a rain gauge" in result["text"]
    assert "does not confirm flooding at your location" in result["text"]


def test_no_severity_word_is_ever_attached_to_the_number():
    """IMD's daily bands are official language this estimate has not earned."""
    result = describe(rainfall(window(24, 250)))
    for word in ("heavy rain over", "very heavy", "extremely heavy", "moderate"):
        assert word not in result["headline"].lower()
    assert "about 250 mm" in result["headline"]


def test_a_trace_of_rain_is_never_rounded_down_to_zero_millimetres():
    result = describe(rainfall(window(24, "0.4")))
    assert "less than 1 mm" in result["headline"]
    assert "0 mm" not in result["headline"]


def test_the_source_and_run_travel_with_the_sentence():
    result = describe(rainfall(window(24, 10), run=ImergRun.EARLY))
    assert result["attribution"] == "NASA GPM IMERG (early run)"
    assert result["run"] == "early"


# --- what it says when the preferred window is missing --------------------


def test_it_falls_back_to_the_longest_window_that_actually_exists():
    result = describe(
        rainfall(
            window(3, 12),
            window(6, 20),
            window(24, reason=REASON_WINDOW_NOT_COVERED),
        )
    )
    assert result["window_hours"] == 6
    assert "the last 6 hours" in result["headline"]
    assert result["total_precipitation_mm"] == pytest.approx(20.0)


def test_the_label_never_claims_a_window_it_did_not_use():
    result = describe(
        rainfall(window(1, 5), window(24, reason=REASON_WINDOW_NOT_COVERED))
    )
    assert "the last hour" in result["headline"]
    assert "24 hours" not in result["headline"]


# --- what it says when there is nothing ----------------------------------


def test_no_estimate_is_said_in_words_rather_than_left_blank():
    result = describe(
        rainfall(
            window(1, reason=REASON_MISSING_CELLS),
            window(24, reason=REASON_MISSING_CELLS),
        )
    )
    assert result["status"] == "unavailable"
    assert result["total_precipitation_mm"] is None
    assert "No satellite rainfall estimate is available" in result["headline"]
    assert "Part of this area has no reading" in result["headline"]


def test_a_missing_estimate_never_reads_as_no_rain():
    result = describe(rainfall(window(24, reason=REASON_WINDOW_NOT_COVERED)))
    assert "0 mm" not in result["text"]
    assert "no rain" not in result["text"].lower()
    assert "most recent readings have not arrived" in result["headline"]


# --- age -----------------------------------------------------------------


def test_a_fresh_late_run_estimate_is_presented_as_the_current_picture():
    result = describe(rainfall(window(24, 30)), now=AS_OF + timedelta(hours=14))
    assert result["status"] == "estimate"
    assert "Nothing newer" not in result["headline"]


def test_an_estimate_that_has_fallen_behind_names_the_period_it_covers():
    result = describe(rainfall(window(24, 30)), now=AS_OF + timedelta(hours=30))
    assert result["status"] == "stale_estimate"
    assert "Nothing newer has arrived" in result["headline"]
    # 12:00 UTC is 5:30 PM IST.
    assert "5:30 PM on 6 Aug" in result["headline"]
    assert result["age_hours"] == pytest.approx(30.0)


def test_the_early_run_goes_stale_sooner_than_the_late_run():
    """Early is the four-hour product; the same age means different things."""
    late = describe(rainfall(window(24, 30)), now=AS_OF + timedelta(hours=12))
    early = describe(
        rainfall(window(24, 30), run=ImergRun.EARLY), now=AS_OF + timedelta(hours=12)
    )
    assert late["status"] == "estimate"
    assert early["status"] == "stale_estimate"
