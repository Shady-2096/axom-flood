"""Measure how well a circle outline agrees with points that were placed independently.

The question this answers
------------------------
An outline is only worth computing against if the places it claims are actually
inside it. The repository already holds a large set of points whose position was
decided without ever consulting a boundary: UDISE school coordinates, joined to a
Census village by name and district, and through that village to a revenue
circle. If a circle's own schools fall inside its own outline, the outline is
describing the right piece of ground.

What must not be used
---------------------
`config/assam-village-search-index.json` gives every village a `centre`, but two
thirds of them carry `centre_confidence: "revenue_circle_fallback"` — the
coordinate was filled in from the circle itself because no school matched. Those
points cannot test a boundary; they would only ask the circle whether it agrees
with itself. They are excluded, which is why 6,184 points are available here and
not the roughly 26,000 the master plan assumed.

School points rather than village medians
-----------------------------------------
A village's stored centre is the median of its schools. Scoring against the
individual schools instead uses the same evidence at full resolution, gives small
circles enough points to say anything at all, and exposes the villages whose name
match pulled in a school from the other end of the state.

What a score is not
-------------------
A low score means the outline and the school points disagree. It does not say
which of them is wrong: a village name matched to a school in a different
district produces exactly the same signal as a misdrawn boundary. Any circle that
fails is a circle to look at, not a circle proved bad.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from math import ceil, cos, floor, radians
from pathlib import Path

from axom_flood.geometry import Ring, point_in_rings

# Below this many independent points a percentage is not evidence. Twelve is not
# a statistical threshold; it is the point at which one bad village name stops
# being able to swing the result by more than about eight points.
MIN_POINTS_FOR_A_SCORE = 12


def fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


@dataclass
class CircleScore:
    locality_id: str
    points: int
    inside: int
    villages: int

    @property
    def agreement(self) -> float | None:
        return None if not self.points else self.inside / self.points

    @property
    def has_enough_points(self) -> bool:
        return self.points >= MIN_POINTS_FOR_A_SCORE


# The village index records the Census 2011 district; UDISE records the district
# as it is filed today. Two things have to be crossed to join them.
#
# Spelling, where the same district is written differently:
UDISE_SPELLINGS = {
    "kamrup": "kamruprural",
    "kamrupmetropolitan": "kamrupmetro",
    "sivasagar": "sibsagar",
}
# And district creation, where UDISE files a school under a district that did not
# exist in 2011. A village the Census puts in Nagaon may be filed by UDISE under
# Hojai, so the parent's name alone finds nothing — which is why every circle in
# Hojai, Charaideo, Majuli and South Salmara-Mankachar scored zero points before
# this table existed.
UDISE_SUCCESSORS = {
    "nagaon": ("hojai",),
    "sonitpur": ("biswanath",),
    "jorhat": ("majuli",),
    "sivasagar": ("charaideo",),
    "dhubri": ("southsalmaramankachar",),
    "karbianglong": ("westkarbianglong",),
    "barpeta": ("bajali",),
    "baksa": ("tamulpur",),
    "kamrup": ("kamrupmetro",),
}


def school_points_by_locality(
    village_index: list[dict], udise_csv: Path
) -> dict[str, list[tuple[float, float]]]:
    """Every UDISE school coordinate, keyed by the locality its village belongs to.

    A school belongs to the village whose folded name and district it records.
    Villages whose name matched no school contribute nothing, which is correct —
    they have no independent position.

    A village is registered under every district name UDISE might have filed it
    under — its own, and any district later carved out of it. The safety comes
    from the other side: a district-and-name key claimed by more than one
    locality is dropped rather than counted for both. So if the same village name
    exists in Nagaon and again in Hojai, neither takes the other's schools. A
    wrong point is worse here than a missing one, because it would look exactly
    like a boundary error.
    """
    villages_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for village in village_index:
        district = fold(village["district"])
        names = {UDISE_SPELLINGS.get(district, district)}
        names |= set(UDISE_SUCCESSORS.get(district, ()))
        for name in names:
            villages_by_key[(name, fold(village["village_name"]))].add(
                village["locality_id"]
            )

    schools: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    with udise_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                point = (float(row["longitude"]), float(row["latitude"]))
            except (TypeError, ValueError):
                continue
            schools[(fold(row["district"]), fold(row["village"]))].append(point)

    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for key, owners in schools.items():
        claimants = villages_by_key.get(key)
        # A village name that occurs in two circles cannot say which circle its
        # schools belong to, so it is dropped rather than counted for both.
        if not claimants or len(claimants) != 1:
            continue
        points[next(iter(claimants))].extend(owners)
    return dict(points)


def village_counts(village_index: list[dict]) -> dict[str, int]:
    """How many villages of each locality have an independently derived centre."""
    counts: dict[str, int] = defaultdict(int)
    for village in village_index:
        if village.get("centre_confidence") == "exact_village_school_median":
            counts[village["locality_id"]] += 1
    return dict(counts)


def score_circle(
    locality_id: str,
    rings: list[Ring],
    points: list[tuple[float, float]],
    villages: int = 0,
) -> CircleScore:
    inside = sum(1 for point in points if point_in_rings(list(point), rings))
    return CircleScore(
        locality_id=locality_id, points=len(points), inside=inside, villages=villages
    )


def ring_area(ring: Ring) -> float:
    """Unsigned planar area in square degrees.

    Square degrees are meaningless as an area but perfectly good as a ratio,
    which is all the topology check needs. Assam's latitude range is narrow
    enough that the longitude scaling error does not change which circles overlap.
    """
    total = 0.0
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def outline_area(rings: list[Ring]) -> float:
    return sum(ring_area(ring) for ring in rings)


def bounds(rings: list[Ring]) -> tuple[float, float, float, float]:
    xs = [point[0] for ring in rings for point in ring]
    ys = [point[1] for ring in rings for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


# Roughly 550 m at Assam's latitude. Fine enough that a real overlap between two
# circles is many cells wide, coarse enough that a shared border — which has no
# area at all — cannot register as one.
CELL_DEGREES = 0.005

Cell = tuple[int, int]


def rasterize(rings: list[Ring], step: float = CELL_DEGREES) -> set[Cell]:
    """The grid cells whose centres lie inside an outline.

    Scanline fill rather than testing every cell for containment: one pass along
    each row of the grid gives every span the outline covers on that row, which
    turns a containment test per cell into one sort per row.

    Cells are indexed from a fixed global origin, so two circles rasterised
    separately can be compared cell for cell. Testing pairs of outlines directly
    would mean deciding what a shared boundary vertex means, and adjacent circles
    share thousands of them — that ambiguity is what a cell centre removes.
    """
    edges = [
        (ring[index], ring[(index + 1) % len(ring)])
        for ring in rings
        if len(ring) >= 3
        for index in range(len(ring))
    ]
    if not edges:
        return set()
    ys = [point[1] for edge in edges for point in edge]
    first_row = floor(min(ys) / step) - 1
    last_row = floor(max(ys) / step) + 1

    cells: set[Cell] = set()
    for row in range(first_row, last_row + 1):
        y = (row + 0.5) * step
        crossings: list[float] = []
        for (x1, y1), (x2, y2) in edges:
            if (y1 > y) != (y2 > y):
                crossings.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)
        if not crossings:
            continue
        crossings.sort()
        # Even-odd: consecutive pairs of crossings bound the interior, which is
        # the same rule `point_in_rings` uses and so treats a second ring as a
        # hole or a detached part in exactly the same way.
        for index in range(0, len(crossings) - 1, 2):
            left, right = crossings[index], crossings[index + 1]
            # The cell centred at (column + 0.5) * step, so the first column in
            # the span is the smallest such centre at or after `left`. `int()`
            # truncates towards zero and would drop the first column of any span
            # starting at or below the origin.
            first_col = ceil(left / step - 0.5)
            last_col = floor(right / step - 0.5)
            for column in range(first_col, last_col + 1):
                cells.add((column, row))
    return cells


def cell_of(longitude: float, latitude: float, step: float = CELL_DEGREES) -> Cell:
    """The grid cell a point falls in, indexed the same way `rasterize` does."""
    return floor(longitude / step), floor(latitude / step)


def cell_area_sq_km(row: int, step: float = CELL_DEGREES) -> float:
    """Area of one grid cell in square kilometres.

    A degree of latitude is very close to 110.57 km throughout Assam; a degree of
    longitude shrinks with the cosine of the latitude. Over Assam's four degrees
    of latitude that cosine changes by about four per cent, which matters when
    areas from the north and south of the state are added together.
    """
    latitude = (row + 0.5) * step
    return (step * 110.57) * (step * 111.32 * cos(radians(latitude)))


@dataclass
class Topology:
    """How the circles sit against one another once rasterised."""

    cells: dict[str, set[Cell]]
    overlap_cells: dict[str, dict[str, int]]

    def overlap_share(self, locality_id: str) -> float:
        own = self.cells.get(locality_id) or set()
        if not own:
            return 0.0
        shared = {
            cell
            for other, count in self.overlap_cells.get(locality_id, {}).items()
            if count
            for cell in own & (self.cells.get(other) or set())
        }
        return len(shared) / len(own)


def measure_topology(
    outlines: dict[str, list[Ring]], step: float = CELL_DEGREES
) -> tuple[dict[str, set[Cell]], dict[str, dict[str, int]]]:
    """Rasterise every circle and record which pairs share cells.

    Circles are supposed to tile the state. A pair sharing a meaningful number of
    cells is a duplicate relation, a circle matched to the wrong locality, or a
    genuine OpenStreetMap error — and any of the three makes the outline unsafe to
    compute against.
    """
    cells = {key: rasterize(rings, step) for key, rings in outlines.items()}
    owners: dict[Cell, list[str]] = defaultdict(list)
    for key, filled in cells.items():
        for cell in filled:
            owners[cell].append(key)
    shared: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for claimants in owners.values():
        if len(claimants) < 2:
            continue
        for left in claimants:
            for right in claimants:
                if left != right:
                    shared[left][right] += 1
    return cells, {key: dict(value) for key, value in shared.items()}
