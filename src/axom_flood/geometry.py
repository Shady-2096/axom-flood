"""Planar helpers for revenue-circle outlines.

Assam spans about three degrees of longitude, and every use here is either a
containment test or the choice of one interior point, so the rings are treated
as planar lon/lat. Distance is never computed with these functions; that is
`cwc.pipeline.haversine_km`.
"""

from __future__ import annotations

import json
from pathlib import Path

Point = list[float]
Ring = list[Point]

CIRCLE_SHAPES = Path("config/assam-circle-shapes.json")

# How a circle's stored centroid was arrived at.
SOURCE_METHOD = "median_exact_udise_village_match"
CORRECTED_METHOD = "circle_outline_representative_point"


def point_in_rings(point: Point, rings: list[Ring]) -> bool:
    """Even-odd containment across every ring of a circle.

    Even-odd is what the data needs rather than a simplification: five circles
    are two rings, and the rule gives the right answer whether the second ring is
    a hole (a point inside it crosses twice more, so it falls out) or a detached
    part of the same circle (a point inside it crosses twice, so it falls in).
    """
    x, y = point[0], point[1]
    inside = False
    for ring in rings:
        count = len(ring)
        for index in range(count):
            x1, y1 = ring[index][0], ring[index][1]
            x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _signed_area(ring: Ring) -> float:
    total = 0.0
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _area_centroid(ring: Ring) -> Point | None:
    area = _signed_area(ring)
    if abs(area) < 1e-12:
        return None
    cx = cy = 0.0
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return [cx / (6.0 * area), cy / (6.0 * area)]


def _widest_interior_point(ring: Ring, latitude: float) -> Point | None:
    """Midpoint of the widest span the ring covers along one line of latitude."""
    crossings: list[float] = []
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        if (y1 > latitude) != (y2 > latitude):
            crossings.append((x2 - x1) * (latitude - y1) / (y2 - y1) + x1)
    crossings.sort()
    best: tuple[float, float] | None = None
    for index in range(0, len(crossings) - 1, 2):
        left, right = crossings[index], crossings[index + 1]
        if best is None or right - left > best[0]:
            best = (right - left, (left + right) / 2.0)
    return None if best is None else [best[1], latitude]


def representative_point(rings: list[Ring]) -> Point | None:
    """A point guaranteed to lie inside the circle these rings describe.

    The area-weighted centroid is preferred because it sits where a reader would
    point at the shape. A concave circle — and river-following boundaries are
    very often concave — can put that centroid outside its own outline, so the
    result is verified and a scanline midpoint is used instead when it fails.
    """
    parts = [ring for ring in rings if len(ring) >= 3]
    if not parts:
        return None
    outer = max(parts, key=lambda ring: abs(_signed_area(ring)))

    centroid = _area_centroid(outer)
    if centroid is not None and point_in_rings(centroid, rings):
        return [round(centroid[0], 6), round(centroid[1], 6)]

    latitudes = [point[1] for point in outer]
    candidates = [centroid[1]] if centroid is not None else []
    low, high = min(latitudes), max(latitudes)
    # Sweep rather than trusting one line: a circle pinched at its middle can
    # have no interior span at the centroid's latitude.
    candidates += [low + (high - low) * step / 16.0 for step in range(1, 16)]
    for latitude in candidates:
        point = _widest_interior_point(outer, latitude)
        if point is not None and point_in_rings(point, rings):
            return [round(point[0], 6), round(point[1], 6)]
    return None


def load_circle_outlines(path: Path | None = None) -> dict[str, list[Ring]]:
    """Circle outlines keyed by locality id."""
    document = json.loads((path or CIRCLE_SHAPES).read_text())
    outlines: dict[str, list[Ring]] = {}
    for circle in document.get("circles", []):
        rings = circle.get("rings") or []
        for locality_id in circle.get("locality_ids") or []:
            outlines[locality_id] = rings
    return outlines


def corrected_centre(
    locality_id: str, centre: Point, outlines: dict[str, list[Ring]]
) -> tuple[Point, str]:
    """The centroid to store for one circle, and how it was arrived at.

    `build_localities.py` derives a centroid as the median position of the UDISE
    village points whose names matched the circle. Where that name match picked
    up villages elsewhere in the state the median lands outside the circle
    entirely — Gohpur's sat 100 km west, in the Tezpur area — and the map then
    drew its gauge line from there and reported the distance to that point.

    Only a centroid that is genuinely outside its own outline is replaced. One
    that sits inside is kept even when it is nowhere near the town of the same
    name: a circle is an area, and its centre is allowed not to be its namesake.

    This widens what the outlines are used for. Their provenance note says they
    are for drawing and "are not used to place anyone", which still holds — this
    places a circle's own centre, never a person, a camp, or a gauge, and it
    never chooses which gauge a circle reads.
    """
    rings = outlines.get(locality_id)
    if not rings or point_in_rings(centre, rings):
        return centre, SOURCE_METHOD
    replacement = representative_point(rings)
    if replacement is None:
        return centre, SOURCE_METHOD
    return replacement, CORRECTED_METHOD
