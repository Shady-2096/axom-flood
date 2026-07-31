"""Offline parser for the approval-gated Google Flood Forecasting API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..rainfall.provenance import (
    SourceRevision,
    parse_aware_datetime,
    require_aware,
)

GOOGLE_FLOOD_DOCUMENTATION_URL = "https://developers.google.com/flood-forecasting"
GOOGLE_FLOOD_API_ROOT = "https://floodforecasting.googleapis.com"


class GoogleFloodAccessDisabled(RuntimeError):
    """The owner has not supplied an approved project and API key."""


@dataclass(frozen=True, slots=True)
class GoogleFloodStatus:
    gauge_id: str
    issued_at: datetime
    forecast_start: datetime
    forecast_end: datetime
    severity: str
    quality_verified: bool
    inundation_set_ids: tuple[str, ...]
    revision: SourceRevision

    def __post_init__(self) -> None:
        require_aware(self.issued_at, "issued_at")
        require_aware(self.forecast_start, "forecast_start")
        require_aware(self.forecast_end, "forecast_end")
        if self.forecast_end <= self.forecast_start:
            raise ValueError("Google Flood forecastEndTime must follow forecastStartTime")
        if not self.gauge_id or not self.severity:
            raise ValueError("Google Flood gaugeId and severity must not be empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": "Google Flood Forecasting API",
            "access_mode": "approval_required",
            "gauge_id": self.gauge_id,
            "issued_at": self.issued_at.isoformat(),
            "forecast_start": self.forecast_start.isoformat(),
            "forecast_end": self.forecast_end.isoformat(),
            "severity": self.severity,
            "quality_verified": self.quality_verified,
            "inundation_set_ids": list(self.inundation_set_ids),
            "source_revision": self.revision.as_dict(),
        }


class GoogleFloodStatusParser:
    """Typed offline boundary; live access remains disabled until approved."""

    def __init__(self, *, live_enabled: bool = False) -> None:
        self.live_enabled = live_enabled

    def require_live_access(self, *, api_key: str | None) -> None:
        if not self.live_enabled or not (api_key or "").strip():
            raise GoogleFloodAccessDisabled(
                "Google Flood live access needs waitlist approval, API enablement, "
                "an approved Cloud project, and an owner-provided API key"
            )

    def parse(
        self,
        content: bytes,
        *,
        fetched_at: datetime,
        source_url: str = GOOGLE_FLOOD_API_ROOT,
    ) -> GoogleFloodStatus:
        revision = SourceRevision.capture(
            content,
            source_id="google-flood-status",
            source_url=source_url,
            fetched_at=fetched_at,
            media_type="application/json",
        )
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Google Flood status must be UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Google Flood status must be an object")

        inundation_sets = payload.get("inundationSets", [])
        if not isinstance(inundation_sets, list):
            raise ValueError("Google Flood inundationSets must be an array")
        identifiers: list[str] = []
        for index, item in enumerate(inundation_sets):
            if isinstance(item, str):
                identifier = item
            elif isinstance(item, dict):
                identifier = item.get("id") or item.get("name")
            else:
                identifier = None
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(f"inundationSets[{index}] has no typed identifier")
            identifiers.append(identifier)

        if not isinstance(payload.get("qualityVerified"), bool):
            raise ValueError("Google Flood qualityVerified must be boolean")
        return GoogleFloodStatus(
            gauge_id=str(payload.get("gaugeId", "")),
            issued_at=parse_aware_datetime(payload.get("issuedTime", ""), "issuedTime"),
            forecast_start=parse_aware_datetime(
                payload.get("forecastStartTime", ""), "forecastStartTime"
            ),
            forecast_end=parse_aware_datetime(
                payload.get("forecastEndTime", ""), "forecastEndTime"
            ),
            severity=str(payload.get("severity", "")),
            quality_verified=payload["qualityVerified"],
            inundation_set_ids=tuple(identifiers),
            revision=revision,
        )
