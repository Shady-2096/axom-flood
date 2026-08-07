"""Area-weighted rainfall aggregation from a lat/lon grid onto revenue circles.

Workstream C of the local-accuracy master plan, and the step Workstream 0 was
blocking. `prepare_imerg_zonal_join` could only ever describe this operation and
hand it to "a geospatial worker", because no circle had a boundary worth
computing against. Eighty-two now do.

What this module is allowed to claim
------------------------------------

An average over a whole circle, and nothing smaller. The boundaries it consumes
were promoted by measurement — a circle's own school points were tested against
its own outline, and it passed at 90% agreement with clean topology. That
supports "how much rain fell over this circle". It does **not** support "is this
house inside the circle", and `MeasuredBoundary` refuses to be used as if it
did. The distinction is already recorded in the review file's own rules and is
mirrored here so the code cannot quietly outgrow it.

Why weights are area, not centre-point
--------------------------------------

An IMERG cell is about 11 km across. Many Assam revenue circles are smaller than
one cell, and most of the rest are a handful. Assigning each cell to whichever
circle contains its centre would give small circles either everything or nothing
from a single cell, and the error does not average out — it is a fixed
misattribution repeated every half hour. Each cell is therefore clipped to the
circle and contributes in proportion to the area actually inside it.

Coverage is all or nothing
--------------------------

If any cell overlapping a circle has no reading, the circle gets no number. The
alternative is averaging the cells that did arrive, which silently reports the
rainfall of part of a circle as the rainfall of the circle — and reads lowest
exactly when a storm sits over the missing cell. The names of the missing cells
travel with the refusal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from math import cos, floor, radians, sin
from pathlib import Path
from typing import Any

from ..geometry import Ring
from .imerg import ImergGridCellObservation, ImergRun, accumulate_imerg_cell

#: Mean Earth radius, WGS-84. Turns the dimensionless line integral below into
#: square kilometres.
_EARTH_RADIUS_KM = 6371.0088

#: IMERG's native grid. Passed explicitly everywhere so a different product, or
#: a synthetic grid in a test, does not need this module changed.
IMERG_CELL_DEGREES = 0.1

#: A clipped cell smaller than this share of the circle contributes nothing. It
#: exists to drop slivers produced by a boundary vertex grazing a cell edge, not
#: to drop real coverage — at 1e-9 of a circle it is well under a square metre.
_SLIVER_SHARE = 1e-9

#: How far the clipped pieces may collectively miss the whole ring before the
#: tiling is treated as broken. Area here is a line integral around the ring, so
#: cutting a ring into pieces splits the integral exactly and the tolerance only
#: has to absorb floating-point noise.
_AREA_CLOSURE_TOLERANCE = 1e-9

#: What a measured boundary may and may not be used for. These are the strings
#: from `data/review/circle-boundaries/current.json`, kept identical on purpose:
#: one rule, written once, checked in both places.
ZONAL_PERMITS = (
    "averaging a value over the whole circle — rainfall, a terrain band, a "
    "share of low ground"
)
ZONAL_FORBIDS = (
    "deciding whether an individual point, household, or report lies inside "
    "the circle; that needs a separate review this score cannot stand in for"
)


class BoundaryGradeError(ValueError):
    """An analytical boundary was asked for something its grade does not support."""


class CoverageError(ValueError):
    """A circle's cells are not all present, so no circle-wide number exists."""


@dataclass(frozen=True, slots=True)
class MeasuredBoundary:
    """A circle outline promoted by measurement rather than by a person.

    Deliberately not a `GeometryReference`. That class gates the satellite,
    GloFAS and MERIT joins behind `require_reviewed`, which demands a named
    human and a review time. No human reviewed these outlines; a script scored
    them. Making this a `GeometryReference` with `review_status="reviewed"`
    would need a reviewer's name that does not exist, and would loosen a guard
    three other modules rely on. So it is a separate thing that says what it
    actually is, and it is accepted only where measurement is enough.
    """

    locality_id: str
    revenue_circle: str
    district: str
    rings: tuple[Ring, ...]
    grade: str
    agreement: float
    independent_points: int
    snapshot_sha256: str
    osm_id: str

    def __post_init__(self) -> None:
        if not self.rings or not all(len(ring) >= 4 for ring in self.rings):
            raise ValueError(f"{self.locality_id} boundary has no usable ring")
        if not 0.0 <= self.agreement <= 1.0:
            raise ValueError(f"{self.locality_id} agreement must be a share")

    def require_zonal_grade(self, purpose: str) -> None:
        if self.grade != "zonal":
            raise BoundaryGradeError(
                f"{purpose} needs a circle at zonal grade; {self.locality_id} is "
                f"{self.grade!r}"
            )

    def refuse_individual_placement(self, purpose: str) -> None:
        """Always raises. Present so the refusal is a call site, not a comment."""
        raise BoundaryGradeError(
            f"{purpose} is not supported by a measured boundary: {ZONAL_FORBIDS}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "locality_id": self.locality_id,
            "revenue_circle": self.revenue_circle,
            "district": self.district,
            "grade": self.grade,
            "agreement": self.agreement,
            "independent_points": self.independent_points,
            "boundary_sha256": self.snapshot_sha256,
            "osm_id": self.osm_id,
            "promoted_by": "measurement",
            "permits": ZONAL_PERMITS,
            "forbids": ZONAL_FORBIDS,
        }


@dataclass(frozen=True, slots=True)
class CellWeight:
    """One grid cell's share of one circle."""

    grid_cell_id: str
    longitude: float
    latitude: float
    share: float
    area_sq_km: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "grid_cell_id": self.grid_cell_id,
            "longitude": round(self.longitude, 4),
            "latitude": round(self.latitude, 4),
            "share": round(self.share, 8),
            "area_sq_km": round(self.area_sq_km, 4),
        }


@dataclass(frozen=True, slots=True)
class ZonalWeights:
    """Every cell touching one circle, with shares that sum to one."""

    locality_id: str
    cell_degrees: float
    weights: tuple[CellWeight, ...]
    circle_area_sq_km: float
    boundary_sha256: str

    @property
    def cell_ids(self) -> tuple[str, ...]:
        return tuple(weight.grid_cell_id for weight in self.weights)

    def as_dict(self) -> dict[str, Any]:
        return {
            "locality_id": self.locality_id,
            "cell_degrees": self.cell_degrees,
            "circle_area_sq_km": round(self.circle_area_sq_km, 3),
            "boundary_sha256": self.boundary_sha256,
            "cell_count": len(self.weights),
            "cells": [weight.as_dict() for weight in self.weights],
        }


@dataclass(frozen=True, slots=True)
class ZonalAccumulation:
    """Circle-wide rainfall over one window, and the evidence behind it."""

    locality_id: str
    run: ImergRun
    interval_start: Any
    interval_end: Any
    total_mm: Decimal
    cell_count: int
    boundary_sha256: str
    source_revision_sha256s: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "locality_id": self.locality_id,
            "run": self.run.value,
            "interval_start": self.interval_start.isoformat(),
            "interval_end": self.interval_end.isoformat(),
            "total_precipitation_mm": float(self.total_mm),
            "aggregation": "area_weighted_mean_over_circle",
            "cell_count": self.cell_count,
            "boundary_sha256": self.boundary_sha256,
            "source_revision_sha256s": list(self.source_revision_sha256s),
            "permits": ZONAL_PERMITS,
            "forbids": ZONAL_FORBIDS,
        }


def grid_cell_id(longitude: float, latitude: float, cell_degrees: float) -> str:
    """Name a cell by its own south-west corner, so the name cannot drift.

    Naming a cell after its centre invites a half-cell offset the first time
    somebody assumes centres sit on multiples of the cell size. Corners always
    do.
    """

    west = floor(round(longitude / cell_degrees, 9)) * cell_degrees
    south = floor(round(latitude / cell_degrees, 9)) * cell_degrees
    return f"{west:.4f}_{south:.4f}"


def _clip_to_rectangle(
    ring: Ring, west: float, south: float, east: float, north: float
) -> Ring:
    """Sutherland-Hodgman clip of a ring against one axis-aligned cell.

    The clip region is a rectangle and therefore convex, which is all this
    algorithm requires. A concave circle that enters the cell more than once
    comes back as a single ring joined by edges lying exactly on the cell
    boundary; those edges enclose no area, so the shoelace total stays correct.
    """

    def clip_edge(subject: Ring, inside, intersect) -> Ring:
        if not subject:
            return []
        output: Ring = []
        previous = subject[-1]
        previous_inside = inside(previous)
        for current in subject:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersect(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersect(previous, current))
            previous, previous_inside = current, current_inside
        return output

    def cut(subject: Ring, axis: int, bound: float, keep_greater: bool) -> Ring:
        def inside(point):
            return point[axis] >= bound if keep_greater else point[axis] <= bound

        def intersect(start, end):
            span = end[axis] - start[axis]
            if span == 0:
                return (bound, start[1]) if axis == 0 else (start[0], bound)
            t = (bound - start[axis]) / span
            other = 1 - axis
            value = start[other] + t * (end[other] - start[other])
            return (bound, value) if axis == 0 else (value, bound)

        return clip_edge(subject, inside, intersect)

    clipped = list(ring)
    clipped = cut(clipped, 0, west, True)
    clipped = cut(clipped, 0, east, False)
    clipped = cut(clipped, 1, south, True)
    clipped = cut(clipped, 1, north, False)
    return clipped


def _area_sq_km(ring: Ring) -> float:
    """Exact area of a ring whose edges are straight in longitude/latitude.

    Green's theorem on the sphere: the area element cos(φ)dφdλ integrates to the
    boundary integral −∮sin(φ)dλ, and each edge's contribution has a closed form
    because φ varies linearly with λ along it.

    An earlier version scaled a planar shoelace area by the cosine of the ring's
    *mean vertex latitude*, and it was subtly wrong in a way worth recording.
    Clipping changes how many vertices a piece has and duplicates some of them,
    so two pieces covering identical latitude bands averaged to different
    latitudes and drew different cosines. A circle split exactly in half across a
    cell edge came out 0.750016 / 0.249984 instead of 0.75 / 0.25. Small, but it
    was a bias in the weights themselves, and it would have moved every rainfall
    number by a little with no way to notice from the output.

    This form has no mean latitude to get wrong, and being a line integral it is
    exactly additive: the pieces of a clipped ring sum to the whole ring.
    """

    if len(ring) < 3:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:] + ring[:1], strict=False):
        delta_lambda = radians(lon2 - lon1)
        if delta_lambda == 0.0:
            continue
        phi1, phi2 = radians(lat1), radians(lat2)
        if abs(phi2 - phi1) < 1e-14:
            total += delta_lambda * sin(phi1)
        else:
            total += delta_lambda * (cos(phi1) - cos(phi2)) / (phi2 - phi1)
    return abs(total) * _EARTH_RADIUS_KM * _EARTH_RADIUS_KM


def cell_weights(
    boundary: MeasuredBoundary, *, cell_degrees: float = IMERG_CELL_DEGREES
) -> ZonalWeights:
    """Every cell overlapping the circle, weighted by the area inside it."""

    boundary.require_zonal_grade("rainfall zonal aggregation")
    if cell_degrees <= 0:
        raise ValueError("cell_degrees must be positive")

    longitudes = [point[0] for ring in boundary.rings for point in ring]
    latitudes = [point[1] for ring in boundary.rings for point in ring]
    west_index = floor(round(min(longitudes) / cell_degrees, 9))
    east_index = floor(round(max(longitudes) / cell_degrees, 9))
    south_index = floor(round(min(latitudes) / cell_degrees, 9))
    north_index = floor(round(max(latitudes) / cell_degrees, 9))

    circle_area = sum(_area_sq_km(ring) for ring in boundary.rings)
    if circle_area <= 0:
        raise ValueError(f"{boundary.locality_id} boundary encloses no area")

    pieces: list[CellWeight] = []
    clipped_area = 0.0
    for x in range(west_index, east_index + 1):
        for y in range(south_index, north_index + 1):
            west = x * cell_degrees
            south = y * cell_degrees
            east = west + cell_degrees
            north = south + cell_degrees
            area = 0.0
            for ring in boundary.rings:
                clipped = _clip_to_rectangle(ring, west, south, east, north)
                area += _area_sq_km(clipped)
            clipped_area += area
            if area <= 0 or area / circle_area < _SLIVER_SHARE:
                continue
            pieces.append(
                CellWeight(
                    grid_cell_id=grid_cell_id(west, south, cell_degrees),
                    longitude=west + cell_degrees / 2,
                    latitude=south + cell_degrees / 2,
                    share=0.0,
                    area_sq_km=area,
                )
            )

    clipped_total = sum(piece.area_sq_km for piece in pieces)
    if clipped_total <= 0:
        raise ValueError(f"{boundary.locality_id} boundary covers no grid cell")
    drift = abs(clipped_area - circle_area) / circle_area
    if drift > _AREA_CLOSURE_TOLERANCE:
        raise ValueError(
            f"{boundary.locality_id} cells cover {clipped_area:.6f} sq km of a "
            f"{circle_area:.6f} sq km circle; the clip is dropping area"
        )

    weighted = tuple(
        CellWeight(
            grid_cell_id=piece.grid_cell_id,
            longitude=piece.longitude,
            latitude=piece.latitude,
            share=piece.area_sq_km / clipped_total,
            area_sq_km=piece.area_sq_km,
        )
        for piece in sorted(pieces, key=lambda item: item.grid_cell_id)
    )
    return ZonalWeights(
        locality_id=boundary.locality_id,
        cell_degrees=cell_degrees,
        weights=weighted,
        circle_area_sq_km=circle_area,
        boundary_sha256=boundary.snapshot_sha256,
    )


def aggregate_over_circle(
    weights: ZonalWeights,
    observations: list[ImergGridCellObservation],
) -> ZonalAccumulation:
    """Area-weighted rainfall over one circle, or nothing if a cell is missing."""

    if not observations:
        raise CoverageError(f"{weights.locality_id} received no observations")

    by_cell: dict[str, list[ImergGridCellObservation]] = {}
    for observation in observations:
        by_cell.setdefault(observation.grid_cell_id, []).append(observation)

    wanted = set(weights.cell_ids)
    missing = sorted(wanted - by_cell.keys())
    if missing:
        raise CoverageError(
            f"{weights.locality_id} has no reading for {len(missing)} of "
            f"{len(wanted)} cells ({', '.join(missing[:5])}"
            f"{', …' if len(missing) > 5 else ''}); refusing a partial average"
        )
    extra = sorted(by_cell.keys() - wanted)
    if extra:
        raise CoverageError(
            f"{weights.locality_id} was given cells outside its own boundary: "
            f"{', '.join(extra[:5])}"
        )

    total = Decimal(0)
    revisions: list[str] = []
    windows: list[tuple[Any, Any]] = []
    runs: set[ImergRun] = set()
    for weight in weights.weights:
        cell = accumulate_imerg_cell(by_cell[weight.grid_cell_id])
        total += cell.total_mm * Decimal(str(weight.share))
        revisions.extend(cell.source_revision_sha256s)
        windows.append((cell.interval_start, cell.interval_end))
        runs.add(cell.run)

    if len(runs) != 1:
        raise CoverageError(
            f"{weights.locality_id} mixes IMERG runs; Early and Late are "
            "different products and cannot be averaged together"
        )
    starts = {window[0] for window in windows}
    ends = {window[1] for window in windows}
    if len(starts) != 1 or len(ends) != 1:
        raise CoverageError(
            f"{weights.locality_id} cells cover different time windows; "
            "refusing to present them as one accumulation"
        )

    return ZonalAccumulation(
        locality_id=weights.locality_id,
        run=runs.pop(),
        interval_start=starts.pop(),
        interval_end=ends.pop(),
        total_mm=total,
        cell_count=len(weights.weights),
        boundary_sha256=weights.boundary_sha256,
        source_revision_sha256s=tuple(dict.fromkeys(revisions)),
    )


def load_measured_boundaries(
    geojson_path: Path, review_path: Path
) -> list[MeasuredBoundary]:
    """Read the circles Workstream 0 promoted, and only those."""

    collection = json.loads(geojson_path.read_text())
    review = json.loads(review_path.read_text())
    snapshot = review["provenance"]["boundary_sha256"]
    scored = {record["locality_id"]: record for record in review["records"]}

    boundaries: list[MeasuredBoundary] = []
    for feature in collection.get("features", []):
        properties = feature.get("properties", {})
        locality_id = properties.get("locality_id")
        record = scored.get(locality_id)
        if record is None:
            raise ValueError(f"{locality_id} has a boundary but no quality record")
        geometry = feature.get("geometry", {})
        if geometry.get("type") == "Polygon":
            rings = geometry["coordinates"]
        elif geometry.get("type") == "MultiPolygon":
            rings = [ring for polygon in geometry["coordinates"] for ring in polygon]
        else:
            raise ValueError(f"{locality_id} has unsupported geometry")
        boundaries.append(
            MeasuredBoundary(
                locality_id=locality_id,
                revenue_circle=properties.get("revenue_circle", ""),
                district=properties.get("district", ""),
                rings=tuple(
                    [(float(x), float(y)) for x, y in ring] for ring in rings
                ),
                grade=properties.get("grade", ""),
                agreement=float(record["agreement"]),
                independent_points=int(record["independent_points"]),
                snapshot_sha256=snapshot,
                osm_id=properties.get("osm_id", ""),
            )
        )
    return boundaries
