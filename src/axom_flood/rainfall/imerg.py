"""Typed IMERG Early/Late records with unit-safe time aggregation.

IMERG precipitation is a rate in millimetres per hour. A half-hour value is
therefore *not* itself a millimetre accumulation: each rate is multiplied by
its exact interval duration before totals are added.

This module only aggregates one native grid cell through time. It does not
pretend that a grid-cell centre identifies a revenue circle. Preparing a zonal
join is a separate, review-gated operation for a geospatial worker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .provenance import (
    GeometryReference,
    SourceRevision,
    parse_aware_datetime,
    require_aware,
)

IMERG_SOURCE_URL = "https://gpm.nasa.gov/data/imerg"
IMERG_LATENCY_URL = (
    "https://gpm.nasa.gov/resources/faq/what-determines-latency-imerg"
)


class ImergRun(StrEnum):
    EARLY = "early"
    LATE = "late"


@dataclass(frozen=True, slots=True)
class ImergRunPolicy:
    run: ImergRun
    product_short_name: str
    minimum_expected_latency_hours: int
    typical_latency_hours: int
    use_note: str


IMERG_POLICIES = {
    ImergRun.EARLY: ImergRunPolicy(
        run=ImergRun.EARLY,
        product_short_name="GPM_3IMERGHHE.07",
        minimum_expected_latency_hours=4,
        typical_latency_hours=4,
        use_note="lowest-latency research precipitation estimate; revision expected",
    ),
    ImergRun.LATE: ImergRunPolicy(
        run=ImergRun.LATE,
        product_short_name="GPM_3IMERGHHL.07",
        minimum_expected_latency_hours=12,
        typical_latency_hours=14,
        use_note="later research precipitation estimate; not a four-hour product",
    ),
}


@dataclass(frozen=True, slots=True)
class ImergGridCellObservation:
    grid_cell_id: str
    longitude: float
    latitude: float
    interval_start: datetime
    interval_end: datetime
    precipitation_rate_mm_per_hour: Decimal
    run: ImergRun
    product_version: str
    revision: SourceRevision

    def __post_init__(self) -> None:
        require_aware(self.interval_start, "interval_start")
        require_aware(self.interval_end, "interval_end")
        if self.interval_end <= self.interval_start:
            raise ValueError("IMERG interval_end must be after interval_start")
        if self.precipitation_rate_mm_per_hour < 0:
            raise ValueError("IMERG precipitation rate must be non-negative")
        if not -180 <= self.longitude <= 180 or not -90 <= self.latitude <= 90:
            raise ValueError("IMERG grid-cell coordinates are out of range")

    @property
    def interval_hours(self) -> Decimal:
        seconds = Decimal(str((self.interval_end - self.interval_start).total_seconds()))
        return seconds / Decimal(3600)

    @property
    def accumulated_mm(self) -> Decimal:
        return self.precipitation_rate_mm_per_hour * self.interval_hours


@dataclass(frozen=True, slots=True)
class ImergCellAccumulation:
    grid_cell_id: str
    run: ImergRun
    interval_start: datetime
    interval_end: datetime
    total_mm: Decimal
    interval_count: int
    source_revision_sha256s: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "grid_cell_id": self.grid_cell_id,
            "run": self.run.value,
            "interval_start": self.interval_start.isoformat(),
            "interval_end": self.interval_end.isoformat(),
            "total_precipitation_mm": float(self.total_mm),
            "interval_count": self.interval_count,
            "source_revision_sha256s": list(self.source_revision_sha256s),
        }


def parse_imerg_observations(
    content: bytes,
    *,
    fetched_at: datetime,
    source_url: str = IMERG_SOURCE_URL,
) -> list[ImergGridCellObservation]:
    """Parse the small normalized boundary used by the future HDF/GeoTIFF reader."""

    revision = SourceRevision.capture(
        content,
        source_id="nasa-gpm-imerg",
        source_url=source_url,
        fetched_at=fetched_at,
        media_type="application/json",
    )
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("IMERG normalized payload must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ValueError("IMERG payload must contain an observations array")
    if payload.get("units") != "mm/hour":
        raise ValueError("IMERG payload units must be exactly 'mm/hour'")
    if payload.get("product_version") != "07":
        raise ValueError("IMERG adapter is pinned to reviewed product version 07")

    try:
        run = ImergRun(payload["run"])
    except (KeyError, ValueError) as exc:
        raise ValueError("IMERG run must be early or late") from exc
    expected_product = IMERG_POLICIES[run].product_short_name
    if payload.get("product_short_name") != expected_product:
        raise ValueError(
            f"IMERG {run.value} payload must use product short name {expected_product}"
        )

    observations: list[ImergGridCellObservation] = []
    for index, row in enumerate(payload["observations"]):
        if not isinstance(row, dict):
            raise ValueError(f"IMERG observation {index} must be an object")
        try:
            observations.append(
                ImergGridCellObservation(
                    grid_cell_id=str(row["grid_cell_id"]),
                    longitude=float(row["longitude"]),
                    latitude=float(row["latitude"]),
                    interval_start=parse_aware_datetime(
                        row["interval_start"], f"observations[{index}].interval_start"
                    ),
                    interval_end=parse_aware_datetime(
                        row["interval_end"], f"observations[{index}].interval_end"
                    ),
                    precipitation_rate_mm_per_hour=Decimal(
                        str(row["precipitation_rate"])
                    ),
                    run=run,
                    product_version=payload["product_version"],
                    revision=revision,
                )
            )
        except KeyError as exc:
            raise ValueError(f"IMERG observation {index} is missing {exc.args[0]}") from exc
        except (TypeError, ArithmeticError) as exc:
            raise ValueError(f"IMERG observation {index} has an invalid numeric value") from exc
    if not observations:
        raise ValueError("IMERG payload contains no observations")
    return observations


def accumulate_imerg_cell(
    observations: list[ImergGridCellObservation],
) -> ImergCellAccumulation:
    """Convert rate × duration to millimetres for one non-overlapping grid cell."""

    if not observations:
        raise ValueError("at least one IMERG observation is required")
    ordered = sorted(observations, key=lambda item: item.interval_start)
    first = ordered[0]
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.grid_cell_id != first.grid_cell_id:
            raise ValueError("IMERG cell accumulation cannot mix grid_cell_id values")
        if current.run != first.run:
            raise ValueError("IMERG cell accumulation cannot mix Early and Late runs")
        if (current.longitude, current.latitude) != (first.longitude, first.latitude):
            raise ValueError("IMERG grid_cell_id moved coordinates within one accumulation")
        if current.interval_start < previous.interval_end:
            raise ValueError("IMERG intervals overlap; refusing to double-count rainfall")
        if current.interval_start > previous.interval_end:
            raise ValueError("IMERG intervals contain a gap; refusing a partial accumulation")
    if any(item.grid_cell_id != first.grid_cell_id for item in ordered):
        raise ValueError("IMERG cell accumulation cannot mix grid_cell_id values")
    if any(item.run != first.run for item in ordered):
        raise ValueError("IMERG cell accumulation cannot mix Early and Late runs")

    total = sum((item.accumulated_mm for item in ordered), Decimal(0))
    revisions = tuple(dict.fromkeys(item.revision.sha256 for item in ordered))
    return ImergCellAccumulation(
        grid_cell_id=first.grid_cell_id,
        run=first.run,
        interval_start=first.interval_start,
        interval_end=ordered[-1].interval_end,
        total_mm=total,
        interval_count=len(ordered),
        source_revision_sha256s=revisions,
    )


def prepare_imerg_zonal_join(
    observations: list[ImergGridCellObservation],
    *,
    geometry: GeometryReference,
) -> dict[str, Any]:
    """Describe, but do not fabricate, a future grid-to-zone geospatial join."""

    geometry.require_reviewed("IMERG zonal join")
    if not observations:
        raise ValueError("IMERG zonal join requires observations")
    return {
        "schema_version": 1,
        "operation": "imerg_grid_to_reviewed_zone",
        "status": "ready_for_geospatial_worker",
        "geometry": geometry.as_dict(),
        "grid_cell_ids": sorted({item.grid_cell_id for item in observations}),
        "source_revision_sha256s": sorted(
            {item.revision.sha256 for item in observations}
        ),
        "aggregation_contract": "area_weighted; no centre-point assignment",
    }
