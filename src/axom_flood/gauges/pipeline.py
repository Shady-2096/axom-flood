"""Append-only gauge readings with explicit stale and gap states."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
TIME_FIELD = "Data Acquisition Time"
LEVEL_FIELD = "River Water Level Telemetry Hourly (meter)"


def station_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return value or "unknown_station"


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%d-%m-%Y %H:%M").replace(tzinfo=IST)


def compute_trend(
    readings: list[dict[str, Any]],
    *,
    window_hours: int = 4,
    max_gap_minutes: int = 90,
) -> tuple[float | None, bool]:
    if len(readings) < 2:
        return None, False
    latest = readings[-1]["observed_at"]
    window = [
        reading
        for reading in readings
        if latest - reading["observed_at"] <= timedelta(hours=window_hours)
    ]
    if len(window) < 2:
        return None, False
    gap = any(
        current["observed_at"] - previous["observed_at"]
        > timedelta(minutes=max_gap_minutes)
        for previous, current in zip(window, window[1:], strict=False)
    )
    if gap:
        return None, True
    elapsed_hours = (window[-1]["observed_at"] - window[0]["observed_at"]).total_seconds() / 3600
    if elapsed_hours <= 0:
        return None, False
    trend_cm_per_hour = (window[-1]["level_m"] - window[0]["level_m"]) * 100 / elapsed_hours
    return round(trend_cm_per_hour, 2), False


def _append_readings(path: Path, readings: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        existing = {
            json.loads(line)["observed_at"] for line in path.read_text().splitlines() if line
        }
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        for reading in readings:
            observed_at = reading["observed_at"].isoformat()
            if observed_at in existing:
                continue
            serializable = {**reading, "observed_at": observed_at}
            handle.write(json.dumps(serializable, sort_keys=True) + "\n")
            existing.add(observed_at)
            added += 1
    return added


def ingest_gauge_csv(
    *,
    source: str,
    data_dir: Path,
    now: datetime | None = None,
    stale_after_hours: int = 6,
) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        response = httpx.get(
            source,
            follow_redirects=True,
            timeout=120,
            headers={"User-Agent": "AxomFloodData/0.1"},
        )
        response.raise_for_status()
        raw = response.content
    else:
        raw = Path(source).read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    required = {"Station", "District", "Latitude", "Longitude", TIME_FIELD, LEVEL_FIELD}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(f"gauge CSV missing required fields: {sorted(required)}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata: dict[str, dict[str, Any]] = {}
    for row in reader:
        name = row["Station"].strip()
        gauge_id = station_id(name)
        try:
            level = float(row[LEVEL_FIELD])
            observed_at = _parse_time(row[TIME_FIELD])
        except (ValueError, TypeError):
            continue
        grouped[gauge_id].append(
            {
                "schema_version": 1,
                "gauge_id": gauge_id,
                "observed_at": observed_at,
                "level_m": level,
                "source": "NWDP",
                "source_sha256": source_sha256,
            }
        )
        metadata[gauge_id] = {
            "gauge_id": gauge_id,
            "site_name": name,
            "district": row["District"].strip().title(),
            "river": row.get("River", "").strip() or None,
            "coordinates": [float(row["Longitude"]), float(row["Latitude"])],
            "agency": row.get("Agency", "").strip() or None,
            "source_url": source if source.startswith(("http://", "https://")) else None,
        }

    now = now or datetime.now(IST)
    snapshots: list[dict[str, Any]] = []
    total_added = 0
    for gauge_id, readings in grouped.items():
        readings.sort(key=lambda item: item["observed_at"])
        total_added += _append_readings(
            data_dir / "series" / "gauges" / f"{gauge_id}.jsonl", readings
        )
        latest = readings[-1]
        age_hours = (now - latest["observed_at"]).total_seconds() / 3600
        trend, gap_detected = compute_trend(readings)
        snapshots.append(
            {
                "schema_version": 1,
                **metadata[gauge_id],
                "observed_at": latest["observed_at"].isoformat(),
                "level_m": latest["level_m"] if age_hours <= stale_after_hours else None,
                "last_observed_level_m": latest["level_m"],
                "data_age_hours": round(age_hours, 2),
                "trend_cm_per_hr": trend if age_hours <= stale_after_hours else None,
                "trend_window_hrs": 4,
                "gap_detected_in_trend_window": gap_detected,
                "status": "no_data" if age_hours > stale_after_hours else "normal",
                "source_sha256": source_sha256,
            }
        )
    snapshots.sort(key=lambda item: item["gauge_id"])
    document = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "stale_after_hours": stale_after_hours,
        "source_sha256": source_sha256,
        "station_count": len(snapshots),
        "stations_with_no_data": sum(item["status"] == "no_data" for item in snapshots),
        "stations": snapshots,
    }
    output_dir = data_dir / "processed" / "gauges"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = hashlib.sha256(
        (json.dumps(document, sort_keys=True) + "\n").encode()
    ).hexdigest()
    output_path = output_dir / f"{artifact_id}.json"
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return {
        "artifact_id": artifact_id,
        "station_count": len(snapshots),
        "readings_added": total_added,
        "stations_with_no_data": document["stations_with_no_data"],
        "json": str(output_path),
    }
