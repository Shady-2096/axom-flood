"""Phase 1 trigger evaluation, rate limiting, and share artifacts."""

from __future__ import annotations

import hashlib
import json
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .sentence import MAX_PROJECTION_HOURS, generate_sentence

SEVERITY_RANK = {
    "all_clear": 0,
    "info": 1,
    "watch": 2,
    "high": 3,
    "severe": 4,
}
PUSH_COOLDOWN = timedelta(hours=6)


def _hours_to(level: float, target: float, trend_cm_per_hr: float | None) -> float | None:
    if trend_cm_per_hr is None or trend_cm_per_hr <= 0 or target <= level:
        return None
    return (target - level) / (trend_cm_per_hr / 100)


def _projected_within(
    gauge: dict[str, Any],
    target: float | None,
    *,
    hours: int = MAX_PROJECTION_HOURS,
) -> bool:
    if target is None or gauge.get("level_m") is None:
        return False
    forecast = gauge.get("forecast")
    if forecast and forecast.get("forecast_level_m") is not None:
        return float(forecast["forecast_level_m"]) >= float(target)
    estimate = _hours_to(
        float(gauge["level_m"]),
        float(target),
        gauge.get("trend_cm_per_hr"),
    )
    return estimate is not None and estimate <= hours


def _three_below_danger(
    readings: list[dict[str, Any]],
    danger_level_m: float,
) -> bool:
    usable = [item for item in readings if item.get("level_m") is not None]
    return len(usable) >= 3 and all(
        float(item["level_m"]) < danger_level_m for item in usable[-3:]
    )


def _crossed_danger(gauge: dict[str, Any], readings: list[dict[str, Any]]) -> bool:
    danger = gauge.get("danger_level_m")
    level = gauge.get("level_m")
    if danger is None or level is None or float(gauge.get("trend_cm_per_hr") or 0) <= 0:
        return False
    earlier = [item for item in readings[:-1] if item.get("level_m") is not None]
    return bool(earlier) and float(earlier[-1]["level_m"]) < float(danger) <= float(level)


def _most_recent_reference(gauge: dict[str, Any]) -> float | None:
    references = [
        item
        for item in gauge.get("reference_floods", [])
        if item.get("year") is not None and item.get("peak_m") is not None
    ]
    if not references:
        return None
    return float(max(references, key=lambda item: int(item["year"]))["peak_m"])


def _trigger(
    gauge: dict[str, Any],
    readings: list[dict[str, Any]],
    *,
    active_event: bool,
) -> tuple[str, str, bool] | None:
    if gauge.get("status") == "no_data" or gauge.get("level_m") is None:
        if active_event and float(gauge.get("data_age_hours") or 0) > 6:
            return "info", "No recent gauge reading during an active event", False
        return None

    level = float(gauge["level_m"])
    highest = gauge.get("highest_flood_level_m")
    danger = gauge.get("danger_level_m")
    # CWC's status word is intentionally absent here. Thresholds and approved
    # level forecasts drive alerts; the convenience classification corroborates.
    if highest is not None and (
        level >= float(highest) or _projected_within(gauge, float(highest))
    ):
        return "severe", "At or projected above the official highest flood level", True
    recent_reference = _most_recent_reference(gauge)
    if recent_reference is not None and _projected_within(gauge, recent_reference):
        return "high", "Projected above the most recent reference flood within 12 hours", True
    if _crossed_danger(gauge, readings):
        return "watch", "Crossed the official danger level while rising", True
    if active_event and danger is not None and _three_below_danger(readings, float(danger)):
        return "all_clear", "Three consecutive readings below the danger level", True
    return None


def _push_allowed(
    severity: str,
    *,
    now: datetime,
    previous_push: dict[str, Any] | None,
) -> bool:
    if previous_push is None:
        return True
    elapsed = now - datetime.fromisoformat(previous_push["issued_at"])
    if elapsed >= PUSH_COOLDOWN:
        return True
    return SEVERITY_RANK[severity] > SEVERITY_RANK[previous_push["severity"]]


def evaluate_alert(
    locality: dict[str, Any],
    gauge: dict[str, Any],
    readings: list[dict[str, Any]],
    *,
    now: datetime,
    active_event: bool,
    previous_push: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    trigger = _trigger(gauge, readings, active_event=active_event)
    if trigger is None:
        return None
    severity, reason, push_candidate = trigger
    sentence = generate_sentence(gauge, now=now)
    push = push_candidate and _push_allowed(severity, now=now, previous_push=previous_push)
    headline = {
        "info": "Gauge update unavailable",
        "watch": "River danger-level watch",
        "high": "High river alert",
        "severe": "Severe river alert",
        "all_clear": "River level below danger mark",
    }[severity]
    text = (
        f"{headline} for {locality['revenue_circle']} revenue circle. "
        f"{sentence['text']}"
    )
    stable = {
        "schema_version": 1,
        "issued_at": now.isoformat(),
        "severity": severity,
        "locality_id": locality["locality_id"],
        "gauge_id": gauge["gauge_id"],
        "trigger_reason": reason,
        "headline_en": headline,
        "body_en": sentence["text"],
        "share_text_en": text,
        "headline_as": None,
        "body_as": None,
        "share_text_as": None,
        "assamese_reviewed": False,
        "official_source_url": gauge["source_url"],
        "push": push,
        "push_suppressed_by_rate_limit": push_candidate and not push,
        "expires_at": (now + timedelta(hours=12)).isoformat(),
    }
    stable["alert_id"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True).encode()
    ).hexdigest()
    return stable


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - compatibility with older Pillow
        return ImageFont.load_default()


def _card(alert: dict[str, Any]) -> Image.Image:
    colours = {
        "info": "#5b7188",
        "watch": "#dd8b1f",
        "high": "#d7562d",
        "severe": "#9e2538",
        "all_clear": "#277a63",
    }
    image = Image.new("RGB", (1080, 1080), "#f5f0e4")
    draw = ImageDraw.Draw(image)
    accent = colours[alert["severity"]]
    draw.rectangle((0, 0, 1080, 38), fill=accent)
    draw.text((72, 78), "AXOM FLOOD  /  OFFICIAL DATA TRANSLATED", fill="#18333f", font=_font(28))
    draw.text((72, 160), alert["headline_en"], fill=accent, font=_font(72))
    body = "\n".join(textwrap.wrap(alert["body_en"], width=37))
    draw.multiline_text((72, 285), body, fill="#132d38", font=_font(42), spacing=16)
    draw.line((72, 918, 1008, 918), fill="#9ba9a5", width=2)
    draw.text(
        (72, 952),
        "Check the official CWC source before acting.",
        fill="#425b63",
        font=_font(30),
    )
    draw.text((72, 1004), alert["issued_at"], fill="#66787d", font=_font(24))
    return image


def persist_alert_artifacts(alert: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    """Persist immutable push, plain-text, and 1080px PNG artifacts."""

    artifact_dir = output_dir / alert["alert_id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    push_path = artifact_dir / "push.json"
    text_path = artifact_dir / "share.txt"
    card_path = artifact_dir / "whatsapp-card.png"
    push_document = {
        "schema_version": 1,
        "alert_id": alert["alert_id"],
        "locality_id": alert["locality_id"],
        "severity": alert["severity"],
        "send": alert["push"],
        "title": alert["headline_en"],
        "body": alert["body_en"],
        "url": alert["official_source_url"],
    }
    payloads = {
        push_path: (json.dumps(push_document, indent=2, sort_keys=True) + "\n").encode(),
        text_path: (alert["share_text_en"] + "\n").encode(),
    }
    for path, payload in payloads.items():
        if path.exists() and path.read_bytes() != payload:
            raise RuntimeError(f"refusing to overwrite immutable alert artifact: {path}")
        if not path.exists():
            path.write_bytes(payload)
    if not card_path.exists():
        _card(alert).save(card_path, format="PNG", optimize=True)
    return {
        "push": str(push_path),
        "plain_text": str(text_path),
        "image_card": str(card_path),
    }
