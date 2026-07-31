"""Ingest public SMART AXOM category endpoints without treating stale rows as current."""

from __future__ import annotations

import hashlib
import json
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://api.nesdr.gov.in/asdma"
ENDPOINTS = {
    "high": ("GET", "flood-high.php"),
    "low_to_moderate": ("GET", "flood-low-to-moderate.php"),
    "no_alert": ("GET", "flood-no-alert.php"),
    "flood_watch": ("GET", "flood-watch.php"),
    "low": ("POST", "flood-low.php"),
}
IST = ZoneInfo("Asia/Kolkata")


def _decode(response: httpx.Response) -> Any:
    response.raise_for_status()
    # These endpoints return JSON with a text/html content type.
    return json.loads(response.text)


def ingest_public_flood_alerts(
    *,
    data_dir: Path,
    now: datetime | None = None,
    stale_after_hours: int = 24,
) -> dict[str, Any]:
    now = now or datetime.now(IST)
    raw: dict[str, Any] = {}
    alerts: list[dict[str, Any]] = []
    with httpx.Client(
        follow_redirects=True,
        timeout=30,
        verify=ssl.create_default_context(),
        headers={"User-Agent": "AxomFloodData/0.1"},
    ) as client:
        for severity, (method, endpoint) in ENDPOINTS.items():
            response = client.request(method, f"{BASE_URL}/{endpoint}")
            rows = _decode(response)
            raw[endpoint] = rows
            for row in rows:
                alerts.append(
                    {
                        "schema_version": 1,
                        "severity_category": severity,
                        "district": row.get("district_n") or row.get("district"),
                        "revenue_circle": row.get("rc_name"),
                        "source_alert_value": row.get("alert"),
                    }
                )
        update_rows = _decode(client.get(f"{BASE_URL}/flood-last-update.php"))
        raw["flood-last-update.php"] = update_rows

    if not update_rows or not update_rows[0].get("date"):
        raise ValueError("SMART AXOM feed did not provide a last-update timestamp")
    issued_at = datetime.strptime(update_rows[0]["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    age_hours = (now - issued_at).total_seconds() / 3600
    is_current = age_hours <= stale_after_hours
    for alert in alerts:
        alert["issued_at"] = issued_at.isoformat()
        alert["is_current"] = is_current

    raw_bytes = (json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n").encode()
    source_revision = hashlib.sha256(raw_bytes).hexdigest()
    raw_path = data_dir / "raw" / "smart-axom" / f"{source_revision}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)
    document = {
        "schema_version": 1,
        "source": "SMART AXOM public dashboard API",
        "source_base_url": BASE_URL,
        "source_revision": source_revision,
        "fetched_at": now.isoformat(),
        "issued_at": issued_at.isoformat(),
        "data_age_hours": round(age_hours, 2),
        "status": "current" if is_current else "no_data",
        "operational_warning": (
            None
            if is_current
            else "Public endpoint is stale; rows must not be presented as active warnings."
        ),
        "alert_count": len(alerts),
        "alerts": alerts,
    }
    output_dir = data_dir / "processed" / "smart-axom"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = hashlib.sha256(
        (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode()
    ).hexdigest()
    output_path = output_dir / f"{artifact_id}.json"
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return {
        "artifact_id": artifact_id,
        "alert_count": len(alerts),
        "issued_at": issued_at.isoformat(),
        "data_age_hours": round(age_hours, 2),
        "status": document["status"],
        "json": str(output_path),
        "raw": str(raw_path),
    }
