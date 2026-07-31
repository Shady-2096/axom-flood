"""Deterministic river sentences; no generative model is used in the live path."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MAX_PROJECTION_HOURS = 12


def _hfl_year(gauge: dict[str, Any]) -> int | None:
    if gauge.get("hfl_year") is not None:
        return int(gauge["hfl_year"])
    value = gauge.get("highest_flood_level_date")
    return datetime.fromisoformat(value).year if value else None


def _references(gauge: dict[str, Any]) -> list[dict[str, Any]]:
    references = [
        item
        for item in gauge.get("reference_floods", [])
        if item.get("year") is not None and item.get("peak_m") is not None
    ]
    return sorted(references, key=lambda item: float(item["peak_m"]), reverse=True)


def comparison_text(gauge: dict[str, Any]) -> str:
    level = float(gauge["level_m"])
    danger = gauge.get("danger_level_m")
    warning = gauge.get("warning_level_m")
    highest = gauge.get("highest_flood_level_m")
    highest_year = _hfl_year(gauge)
    references = _references(gauge)

    if highest is not None and level >= float(highest):
        suffix = f" in {highest_year}" if highest_year else ""
        return f"higher than the highest flood level recorded here{suffix}"

    above = [item for item in references if level >= float(item["peak_m"])]
    below = [item for item in references if level < float(item["peak_m"])]
    if above and not below:
        recent = max(above, key=lambda item: int(item["year"]))
        return f"higher than the {recent['year']} flood"
    if above and below:
        lower = max(above, key=lambda item: float(item["peak_m"]))
        upper = min(below, key=lambda item: float(item["peak_m"]))
        return f"between the {lower['year']} and {upper['year']} flood levels"
    if danger is not None and level >= float(danger):
        if references:
            nearest = min(references, key=lambda item: float(item["peak_m"]))
            return f"above the danger mark, but lower than the {nearest['year']} flood"
        return "above the official danger level"
    if warning is not None and level >= float(warning):
        margin = level - float(warning)
        return f"{margin:.2f} m above the warning level, but below the danger level"
    return "below the official warning level"


def trend_text(gauge: dict[str, Any]) -> str:
    rate = gauge.get("trend_cm_per_hr")
    if rate is None:
        return "a continuous trend is not available"
    value = float(rate)
    if abs(value) < 0.5:
        return "steady"
    direction = "rising" if value > 0 else "falling"
    return f"{direction} about {abs(value):g} cm every hour"


def _next_threshold(gauge: dict[str, Any]) -> tuple[float, str] | None:
    level = float(gauge["level_m"])
    candidates: list[tuple[float, str]] = []
    for field, label in [
        ("warning_level_m", "the warning level"),
        ("danger_level_m", "the danger level"),
        ("highest_flood_level_m", "the highest recorded flood level"),
    ]:
        if gauge.get(field) is not None and float(gauge[field]) > level:
            candidates.append((float(gauge[field]), label))
    candidates.extend(
        (float(item["peak_m"]), f"the {item['year']} flood level")
        for item in _references(gauge)
        if float(item["peak_m"]) > level
    )
    return min(candidates) if candidates else None


def outlook_text(gauge: dict[str, Any], *, now: datetime) -> str:
    forecast = gauge.get("forecast")
    if forecast and forecast.get("forecast_level_m") is not None and forecast.get("forecast_for"):
        forecast_for = datetime.fromisoformat(forecast["forecast_for"]).astimezone(IST)
        return (
            f"CWC's official forecast is {float(forecast['forecast_level_m']):.2f} m "
            f"at {forecast_for:%-I:%M %p} on {forecast_for:%-d %b}."
        )

    rate = gauge.get("trend_cm_per_hr")
    threshold = _next_threshold(gauge)
    if rate is None or float(rate) <= 0 or threshold is None:
        return "No short-range projection is available."
    metres_per_hour = float(rate) / 100
    hours = (threshold[0] - float(gauge["level_m"])) / metres_per_hour
    if not 0 < hours <= MAX_PROJECTION_HOURS:
        return "No projection is shown beyond 12 hours."
    projected_at = now.astimezone(IST) + timedelta(hours=hours)
    return f"At this rate it passes {threshold[1]} around {projected_at:%-I:%M %p}."


def generate_sentence(gauge: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Return the reviewed-English sentence and structured pieces.

    A stale/no-data snapshot never includes the last observed number, trend, or
    CWC convenience classification.
    """

    source_url = gauge["source_url"]
    if gauge.get("status") == "no_data" or gauge.get("level_m") is None:
        text = (
            f"No recent reading is available for {gauge['river']} at {gauge['site_name']}. "
            f"Official source: {source_url}"
        )
        return {
            "language": "en",
            "status": "no_data",
            "text": text,
            "current_state": "No recent reading is available.",
            "comparison": None,
            "trend": None,
            "outlook": None,
            "official_source_url": source_url,
        }

    comparison = comparison_text(gauge)
    trend = trend_text(gauge)
    outlook = outlook_text(gauge, now=now)
    current = (
        f"{gauge['river']} at {gauge['site_name']} is {float(gauge['level_m']):.2f} m, "
        f"{comparison}, and {trend}."
    )
    return {
        "language": "en",
        "status": gauge["status"],
        "text": f"{current} {outlook} Official source: {source_url}",
        "current_state": current,
        "comparison": comparison,
        "trend": trend,
        "outlook": outlook,
        "official_source_url": source_url,
    }
