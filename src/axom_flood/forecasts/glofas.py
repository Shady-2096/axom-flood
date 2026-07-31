"""Strict GloFAS v4.5 30-day gridded advisory contract.

GloFAS output is model guidance, not an authorised warning. This boundary
retains that disclaimer in every normalized document.

On the horizon: GloFAS issues one forecast that runs to 30 days. Days 1-15 come
from the higher-resolution ECMWF ensemble (roughly 18 km) and days 16-30 from
the coarser extended range (roughly 36 km). An earlier revision of this module
capped the contract at 15 days, which silently discarded half of every
forecast. Each value is now tagged with the tier it came from so the two spans
can be labelled differently for readers and never presented with equal
confidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..rainfall.provenance import (
    GeometryReference,
    SourceRevision,
    parse_aware_datetime,
    require_aware,
)

GLOFAS_DATASET_URL = (
    "https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview"
)
GLOFAS_LICENSE_URL = "https://cds.climate.copernicus.eu/licences/cems-floods"
GLOFAS_OPERATIONAL_VERSION = "4.5"
#: Full issued horizon. Days beyond this are a different product.
GLOFAS_HORIZON_DAYS = 30
#: Last day still driven by the higher-resolution ensemble.
GLOFAS_MEDIUM_RANGE_DAYS = 15

MEDIUM_RANGE_TIER = "medium_range"
EXTENDED_RANGE_TIER = "extended_range"


def resolution_tier(issued_at: datetime, valid_at: datetime) -> str:
    """Which half of the forecast a value belongs to.

    Values inside the first 15 days carry the finer ensemble; later ones come
    from the coarser extended range and must be labelled as such.
    """
    if valid_at <= issued_at + timedelta(days=GLOFAS_MEDIUM_RANGE_DAYS):
        return MEDIUM_RANGE_TIER
    return EXTENDED_RANGE_TIER


@dataclass(frozen=True, slots=True)
class GlofasForecastValue:
    valid_at: datetime
    discharge_m3_per_second: float
    #: ``medium_range`` for days 1-15, ``extended_range`` for days 16-30.
    tier: str = MEDIUM_RANGE_TIER

    def __post_init__(self) -> None:
        require_aware(self.valid_at, "valid_at")
        if self.discharge_m3_per_second < 0:
            raise ValueError("GloFAS discharge must be non-negative")
        if self.tier not in {MEDIUM_RANGE_TIER, EXTENDED_RANGE_TIER}:
            raise ValueError(f"unknown GloFAS resolution tier: {self.tier!r}")


@dataclass(frozen=True, slots=True)
class GlofasGridPoint:
    grid_cell_id: str
    longitude: float
    latitude: float
    values: tuple[GlofasForecastValue, ...]

    def __post_init__(self) -> None:
        if not self.grid_cell_id:
            raise ValueError("GloFAS grid_cell_id must not be empty")
        if not -180 <= self.longitude <= 180 or not -90 <= self.latitude <= 90:
            raise ValueError("GloFAS grid coordinates are out of range")
        if not self.values:
            raise ValueError("GloFAS grid point must contain forecast values")


@dataclass(frozen=True, slots=True)
class GlofasGridForecast:
    system_version: str
    issued_at: datetime
    ensemble_statistic: str
    points: tuple[GlofasGridPoint, ...]
    revision: SourceRevision

    def as_advisory_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": "Copernicus Emergency Management Service GloFAS",
            "system_version": self.system_version,
            "issued_at": self.issued_at.isoformat(),
            "forecast_horizon_days": GLOFAS_HORIZON_DAYS,
            "high_resolution_through_day": GLOFAS_MEDIUM_RANGE_DAYS,
            "units": "m3/s",
            "ensemble_statistic": self.ensemble_statistic,
            "advisory_only": True,
            "warning_authority": False,
            "disclaimer": (
                "Model guidance only. National and regional authorities issue flood warnings."
            ),
            "source_revision": self.revision.as_dict(),
            "grid_points": [
                {
                    "grid_cell_id": point.grid_cell_id,
                    "coordinates": [point.longitude, point.latitude],
                    "values": [
                        {
                            "valid_at": value.valid_at.isoformat(),
                            "discharge_m3_per_second": value.discharge_m3_per_second,
                            "resolution_tier": value.tier,
                        }
                        for value in point.values
                    ],
                }
                for point in self.points
            ],
        }


def parse_glofas_grid_forecast(
    content: bytes,
    *,
    fetched_at: datetime,
    source_url: str = GLOFAS_DATASET_URL,
) -> GlofasGridForecast:
    revision = SourceRevision.capture(
        content,
        source_id="cems-glofas-medium-range",
        source_url=source_url,
        fetched_at=fetched_at,
        media_type="application/json",
    )
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("GloFAS normalized payload must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("GloFAS normalized payload must be an object")
    if payload.get("dataset") != "cems-glofas-forecast":
        raise ValueError("unexpected GloFAS dataset identifier")
    if payload.get("system_version") != GLOFAS_OPERATIONAL_VERSION:
        raise ValueError(
            "GloFAS system version drifted from reviewed operational version "
            f"{GLOFAS_OPERATIONAL_VERSION}"
        )
    if payload.get("forecast_horizon_days") != GLOFAS_HORIZON_DAYS:
        raise ValueError(
            f"this adapter accepts only the current {GLOFAS_HORIZON_DAYS}-day product"
        )
    if payload.get("units") != "m3/s":
        raise ValueError("GloFAS discharge units must be exactly 'm3/s'")
    if payload.get("ensemble_statistic") not in {
        "ensemble_mean",
        "ensemble_median",
    }:
        raise ValueError(
            "GloFAS discharge must label its ensemble statistic as mean or median"
        )

    issued_at = parse_aware_datetime(payload.get("issued_at", ""), "issued_at")
    horizon = issued_at + timedelta(days=GLOFAS_HORIZON_DAYS)
    rows = payload.get("grid_points")
    if not isinstance(rows, list) or not rows:
        raise ValueError("GloFAS payload must contain grid_points")

    points: list[GlofasGridPoint] = []
    for point_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"grid_points[{point_index}] must be an object")
        values_raw = row.get("values")
        if not isinstance(values_raw, list) or not values_raw:
            raise ValueError(f"grid_points[{point_index}].values must be non-empty")
        values: list[GlofasForecastValue] = []
        for value_index, value in enumerate(values_raw):
            if not isinstance(value, dict):
                raise ValueError(
                    f"grid_points[{point_index}].values[{value_index}] must be an object"
                )
            valid_at = parse_aware_datetime(
                value.get("valid_at", ""),
                f"grid_points[{point_index}].values[{value_index}].valid_at",
            )
            if valid_at < issued_at or valid_at > horizon:
                raise ValueError(
                    f"GloFAS value falls outside the {GLOFAS_HORIZON_DAYS}-day horizon"
                )
            values.append(
                GlofasForecastValue(
                    valid_at=valid_at,
                    discharge_m3_per_second=float(
                        value["discharge_m3_per_second"]
                    ),
                    tier=resolution_tier(issued_at, valid_at),
                )
            )
        if values != sorted(values, key=lambda item: item.valid_at):
            raise ValueError("GloFAS forecast values must be chronological")
        coordinates = row.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError(f"grid_points[{point_index}].coordinates must be [lon, lat]")
        points.append(
            GlofasGridPoint(
                grid_cell_id=str(row.get("grid_cell_id", "")),
                longitude=float(coordinates[0]),
                latitude=float(coordinates[1]),
                values=tuple(values),
            )
        )
    return GlofasGridForecast(
        system_version=payload["system_version"],
        issued_at=issued_at,
        ensemble_statistic=payload["ensemble_statistic"],
        points=tuple(points),
        revision=revision,
    )


def associate_glofas_reach(
    forecast: GlofasGridForecast,
    *,
    reach_geometry: GeometryReference,
) -> dict[str, Any]:
    """Prepare a reviewed reach/grid association; never use nearest distance."""

    reach_geometry.require_reviewed("GloFAS reach association")
    return {
        "schema_version": 1,
        "operation": "glofas_grid_to_reviewed_reach",
        "status": "ready_for_hydrology_worker",
        "association_rule": (
            "reviewed river topology/upstream area; nearest-grid distance is forbidden"
        ),
        "reach_geometry": reach_geometry.as_dict(),
        "grid_cell_ids": [point.grid_cell_id for point in forecast.points],
        "source_revision_sha256": forecast.revision.sha256,
        "advisory_only": True,
        "warning_authority": False,
    }
