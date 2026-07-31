from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from axom_flood.gauges.pipeline import compute_trend

IST = ZoneInfo("Asia/Kolkata")


def _reading(hour: int, level: float) -> dict:
    return {
        "observed_at": datetime(2026, 7, 25, hour, tzinfo=IST),
        "level_m": level,
    }


def test_trend_is_computed_for_continuous_readings() -> None:
    trend, gap = compute_trend([_reading(1, 10.0), _reading(2, 10.1), _reading(3, 10.2)])
    assert trend == 10
    assert gap is False


def test_trend_is_suppressed_across_gap() -> None:
    readings = [_reading(1, 10.0), _reading(2, 10.1)]
    readings[1]["observed_at"] = readings[0]["observed_at"] + timedelta(hours=3)
    trend, gap = compute_trend(readings)
    assert trend is None
    assert gap is True
