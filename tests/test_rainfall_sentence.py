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


def test_the_headline_leads_with_the_24_hour_window():
    result = describe(rainfall(window(3, 12), window(24, 72)))
    assert result["status"] == "estimate"
    assert result["window_hours"] == 24
    assert "about 72 mm" in result["headline"]
    assert "24 hours" in result["headline"]
    assert "Barama circle" in result["headline"]


def test_the_present_tense_is_used_only_while_it_is_still_true():
    """"The last 24 hours" is a claim about now, not a label for any window.

    The Late run publishes about 15 hours behind by design, so deciding this on
    staleness alone printed a window that had ended most of a day earlier as
    though it had just closed.
    """

    just_closed = describe(
        rainfall(window(24, 72)), now=AS_OF + timedelta(minutes=30)
    )
    assert "the last 24 hours" in just_closed["headline"]

    hours_later = describe(rainfall(window(24, 72)), now=AS_OF + timedelta(hours=6))
    assert "the last 24 hours" not in hours_later["headline"]
    assert "24 hours up to" in hours_later["headline"]


def test_a_normal_wait_is_not_reported_as_a_stalled_pipeline():
    """A source that runs hours behind by design is not broken."""

    result = describe(rainfall(window(24, 72)), now=AS_OF + timedelta(hours=15))
    assert result["status"] == "estimate"
    assert "Nothing newer has arrived" not in result["headline"]
    assert "24 hours up to" in result["headline"]


def test_a_stalled_pipeline_says_so_in_the_sentence():
    result = describe(rainfall(window(24, 72)), now=AS_OF + timedelta(hours=40))
    assert result["status"] == "stale_estimate"
    assert "Nothing newer has arrived" in result["headline"]


def test_the_ageing_sentence_is_always_published_alongside_the_chosen_one():
    """The reader's clock is not the build's clock."""

    result = describe(rainfall(window(24, 72)), now=AS_OF + timedelta(minutes=30))
    assert "the last 24 hours" in result["headline"]
    assert "Nothing newer has arrived" in result["stale_headline"]


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
    assert "the 6 hours up to" in result["headline"]
    assert result["total_precipitation_mm"] == pytest.approx(20.0)


def test_the_label_never_claims_a_window_it_did_not_use():
    result = describe(
        rainfall(window(1, 5), window(24, reason=REASON_WINDOW_NOT_COVERED))
    )
    assert "the hour up to" in result["headline"]
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


# --- the three days behind the last one ----------------------------------


def test_a_dry_day_after_three_wet_ones_does_not_read_as_a_dry_week():
    """The failure this exists for, found in the first real run.

    Kamalpur had the highest 3-day total in Assam at 125 mm and a dry last day,
    so its headline read "less than 1 mm of rain in the 24 hours". Every word
    true, and it hid the only number that mattered.
    """

    result = describe(rainfall(window(24, 0), window(72, 124.6)))

    assert "less than 1 mm" in result["headline"]
    assert "125 mm fell over the 3 days" in result["headline"]
    # The headline window is unchanged. The extra sentence is additive.
    assert result["window_hours"] == 24
    assert result["context_window_hours"] == 72


def test_the_context_sentence_is_absent_when_it_would_add_nothing():
    """A wet day inside a wet three days needs no second number."""

    result = describe(rainfall(window(24, 60), window(72, 64)))

    assert "fell over the 3 days" not in result["headline"]
    assert result["context_window_hours"] is None


def test_a_small_three_day_total_earns_no_extra_sentence():
    result = describe(rainfall(window(24, 0), window(72, 8)))
    assert "fell over the 3 days" not in result["headline"]


def test_the_context_sentence_survives_into_the_stale_wording():
    """A cached artifact read a day later still needs the three-day number. The
    dry day that hid it does not become less misleading with age."""

    result = describe(rainfall(window(24, 0), window(72, 124.6)))
    assert "fell over the 3 days" in result["stale_headline"]


def test_the_context_sentence_is_skipped_when_72_h_is_the_headline():
    """No circle should be told its own number twice."""

    result = describe(rainfall(window(72, 124.6)), preferred_hours=72)
    assert result["window_hours"] == 72
    assert result["headline"].count("124") + result["headline"].count("125") == 1


def test_an_unavailable_three_day_window_adds_nothing():
    result = describe(
        rainfall(window(24, 0), window(72, reason=REASON_MISSING_CELLS))
    )
    assert "fell over the 3 days" not in result["headline"]


def test_the_context_sentence_claims_nothing_about_what_the_rain_means():
    result = describe(rainfall(window(24, 0), window(72, 124.6)))
    for banned in ("heavy", "severe", "danger", "warning", "will flood"):
        assert banned not in result["headline"].casefold()
