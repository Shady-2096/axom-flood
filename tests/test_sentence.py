from datetime import datetime
from zoneinfo import ZoneInfo

from axom_flood.alerts.sentence import generate_sentence

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 27, 20, 0, tzinfo=IST)


def gauge(**overrides):
    value = {
        "gauge_id": "cwc_sivasagar_018_ubddib",
        "river": "Dikhow",
        "site_name": "Sivasagar",
        "status": "above_danger",
        "level_m": 88.0,
        "warning_level_m": 86.2,
        "danger_level_m": 87.2,
        "highest_flood_level_m": 89.1,
        "highest_flood_level_date": "2019-07-15",
        "trend_cm_per_hr": 10.0,
        "forecast": None,
        "reference_floods": [],
        "source_url": "https://ffs.india-water.gov.in/#/station/018-ubddib",
    }
    value.update(overrides)
    return value


def test_sentence_works_with_no_year_by_year_reference_entries() -> None:
    result = generate_sentence(gauge(), now=NOW)
    assert result["comparison"] == "above the official danger level"
    projection = "At this rate it passes the highest recorded flood level around 7:00 AM."
    assert projection in result["text"]
    assert result["official_source_url"] in result["text"]


def test_official_forecast_is_preferred_and_labelled() -> None:
    result = generate_sentence(
        gauge(
            forecast={
                "forecast_level_m": 88.4,
                "forecast_for": "2026-07-28T09:00:00+05:30",
                "issued_at": "2026-07-27T18:00:00+05:30",
            }
        ),
        now=NOW,
    )
    assert "CWC's official forecast" in result["outlook"]
    assert "At this rate" not in result["text"]


def test_warning_sentence_separates_level_from_margin_above_warning() -> None:
    result = generate_sentence(
        gauge(
            river="Brahmaputra",
            site_name="Dhubri",
            status="warning",
            level_m=27.84,
            warning_level_m=27.62,
            danger_level_m=28.62,
            trend_cm_per_hr=0,
        ),
        now=NOW,
    )

    expected = (
        "Brahmaputra at Dhubri is 27.84 m, "
        "0.22 m above the warning level, but below the danger level, and steady."
    )
    assert result["current_state"] == expected
    assert result["comparison"] == "0.22 m above the warning level, but below the danger level"


def test_linear_projection_is_never_shown_past_twelve_hours() -> None:
    result = generate_sentence(gauge(trend_cm_per_hr=1.0), now=NOW)
    assert result["outlook"] == "No projection is shown beyond 12 hours."


def test_stale_snapshot_never_leaks_last_observed_number_or_trend() -> None:
    result = generate_sentence(
        gauge(
            status="no_data",
            level_m=None,
            last_observed_level_m=99.99,
            trend_cm_per_hr=123,
        ),
        now=NOW,
    )
    assert result["status"] == "no_data"
    assert "99.99" not in result["text"]
    assert result["trend"] is None


def test_partial_reference_table_comparisons() -> None:
    references = [
        {"year": 2023, "peak_m": 88.35},
        {"year": 2016, "peak_m": 87.95},
    ]
    result = generate_sentence(gauge(level_m=88.1, reference_floods=references), now=NOW)
    assert result["comparison"] == "between the 2016 and 2023 flood levels"
