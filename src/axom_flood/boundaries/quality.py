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

A point just outside the line is not a disagreement
---------------------------------------------------
Scoring started as a plain containment test, which counted a school 130 m over
the boundary and a school 76 km away as the same evidence. They are not. Measured
across the 97 circles that failed, the strays split into three clean groups: a
median stray under 2 km (the outline and the point differ about exactly where a
shared border runs), a median stray beyond 10 km (the outline covers the wrong
ground, or the school join is wrong), and a cluster 20-50 km out where the
village-name join pulled in schools from another district entirely.

So a point within `TOLERANCE_KM` of the outline counts as agreement. The
justification is the grade being granted, not a wish for more circles to pass.
`zonal` permits averaging a value over a whole circle of a few hundred square
kilometres, and the coarsest consumer is IMERG rainfall on a 0.1-degree grid —
cells about 11 km across. A boundary uncertain by half a kilometre cannot change
which of those cells a circle overlaps.

Half a kilometre is also not a new number. It is the 0.005-degree topology cell
this module already uses, already argued as fine enough to see a real overlap and
coarse enough to ignore a shared border.

The measured curve says the same thing. Passing circles go 61 → 78 → 88 at 0,
250 m, and 500 m, and then 90 at a full kilometre and 92 at two. It is steep to
500 m and flat after, which is what a measurement artefact looks like. A circle
that still fails at 500 m is not rescued by loosening further, so this is not a
slope to slide down.

Both numbers are published. `agreement` is the tolerant one and decides
promotion; `agreement_strict` is the plain containment test, so nobody has to
take the tolerance on trust.

What a score is not
-------------------
A low score means the outline and the school points disagree. It does not say
which of them is wrong: a village name matched to a school in a different
district produces exactly the same signal as a misdrawn boundary. Any circle that
fails is a circle to look at, not a circle proved bad. That is what the stray
distances are for — they say how far the disagreement is, which is the first
thing that separates the two.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from math import ceil, cos, floor, hypot, isinf, radians
from pathlib import Path

from axom_flood.geometry import Ring, point_in_rings

# Below this many independent points a percentage is not evidence. Twelve is not
# a statistical threshold; it is the point at which one bad village name stops
# being able to swing the result by more than about eight points.
MIN_POINTS_FOR_A_SCORE = 12

#: How far outside its own outline a point may sit and still count as agreement.
#: See the module docstring: this is the resolution of the question, not a
#: relaxation of the bar, and it matches the 0.005-degree topology cell below.
TOLERANCE_KM = 0.5

#: A degree of latitude is 110.57 km throughout Assam; a degree of longitude is
#: 111.32 km at the equator and shrinks with the cosine of the latitude. Distance
#: here is only ever compared against a half-kilometre threshold, so a local
#: planar approximation about a fixed reference latitude is ample.
_KM_PER_DEGREE_LAT = 110.57
_KM_PER_DEGREE_LON_EQUATOR = 111.32
#: Assam spans roughly 24-28°N. Taking the middle costs at most about 2% in the
#: longitude scale at the edges, which is centimetres on a 500 m threshold.
_REFERENCE_LATITUDE = 26.0


def fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


@dataclass
class CircleScore:
    locality_id: str
    points: int
    inside: int
    villages: int
    #: Inside, or outside by no more than `TOLERANCE_KM`. Never below `inside`.
    within_tolerance: int = 0
    #: How far outside the outline every point that failed even the tolerant
    #: test landed, in kilometres, ascending. Empty when nothing strayed.
    stray_distances_km: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        # A tolerant test that accepted fewer points than the strict one would
        # mean the distance measure and the containment test disagree about the
        # same polygon, which is a bug rather than a low score.
        self.within_tolerance = max(self.within_tolerance, self.inside)

    @property
    def agreement(self) -> float | None:
        """The share that decides promotion: inside, or within tolerance."""
        return None if not self.points else self.within_tolerance / self.points

    @property
    def agreement_strict(self) -> float | None:
        """The plain containment test, published so the tolerance is inspectable."""
        return None if not self.points else self.inside / self.points

    @property
    def median_stray_km(self) -> float | None:
        """How far the typical real disagreement is. Near means a border; far means
        the outline covers different ground, or the school join is wrong."""
        if not self.stray_distances_km:
            return None
        return self.stray_distances_km[len(self.stray_distances_km) // 2]

    @property
    def max_stray_km(self) -> float | None:
        return self.stray_distances_km[-1] if self.stray_distances_km else None

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


def _segment_distance_km(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Kilometres from a point to a line segment, in the local planar frame."""
    scale_lon = _KM_PER_DEGREE_LON_EQUATOR * cos(radians(_REFERENCE_LATITUDE))
    px, py = point[0] * scale_lon, point[1] * _KM_PER_DEGREE_LAT
    ax, ay = start[0] * scale_lon, start[1] * _KM_PER_DEGREE_LAT
    bx, by = end[0] * scale_lon, end[1] * _KM_PER_DEGREE_LAT
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return hypot(px - ax, py - ay)
    # Projection of the point onto the segment, clamped to its ends so a point
    # beyond a vertex measures to the vertex rather than to the infinite line.
    along = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return hypot(px - (ax + along * dx), py - (ay + along * dy))


def distance_to_outline_km(point: tuple[float, float], rings: list[Ring]) -> float:
    """Shortest distance from a point to any edge of an outline.

    Unsigned: a point just inside and a point just outside measure the same. Only
    ever asked about points already known to be outside, so the sign is not in
    question and computing it would cost a second pass for nothing.

    Two passes. The first skips any segment whose bounding box is further away
    than the tolerance, which answers the only question most points raise — "is
    this within half a kilometre?" — while touching almost no segments. A point
    that rejects every segment is further out than that, and gets a second pass
    over the whole outline to find its real distance. Circle rings run to
    thousands of vertices, so the cheap first pass is what keeps this quick.
    """
    padding = TOLERANCE_KM / _KM_PER_DEGREE_LAT
    longitude, latitude = point
    best = float("inf")
    for ring in rings:
        for index in range(len(ring)):
            start = (ring[index][0], ring[index][1])
            end = (ring[(index + 1) % len(ring)][0], ring[(index + 1) % len(ring)][1])
            if (
                min(start[0], end[0]) - padding > longitude
                or max(start[0], end[0]) + padding < longitude
                or min(start[1], end[1]) - padding > latitude
                or max(start[1], end[1]) + padding < latitude
            ):
                continue
            best = min(best, _segment_distance_km(point, start, end))
    if isinf(best):
        # Nothing survived the rejection, so this point is further out than the
        # tolerance and the fast pass cannot say how much further. That is the
        # common case for a genuinely misplaced point, and the answer still has
        # to be a real distance, so measure again against every segment.
        for ring in rings:
            for index in range(len(ring)):
                best = min(
                    best,
                    _segment_distance_km(
                        point,
                        (ring[index][0], ring[index][1]),
                        (ring[(index + 1) % len(ring)][0], ring[(index + 1) % len(ring)][1]),
                    ),
                )
    return best


def score_circle(
    locality_id: str,
    rings: list[Ring],
    points: list[tuple[float, float]],
    villages: int = 0,
    tolerance_km: float = TOLERANCE_KM,
) -> CircleScore:
    """Count how many of a circle's own points its outline accounts for.

    Two counts, deliberately: `inside` is plain containment, and
    `within_tolerance` also accepts a point sitting no further than
    `tolerance_km` outside. Every point that fails even the tolerant test
    contributes its distance, because how far a stray landed is what separates a
    border drawn slightly differently from an outline over the wrong ground.
    """

    inside = 0
    tolerated = 0
    strays: list[float] = []
    for point in points:
        if point_in_rings(list(point), rings):
            inside += 1
            continue
        distance = distance_to_outline_km(point, rings)
        if distance <= tolerance_km:
            tolerated += 1
        else:
            strays.append(distance)
    return CircleScore(
        locality_id=locality_id,
        points=len(points),
        inside=inside,
        villages=villages,
        within_tolerance=inside + tolerated,
        stray_distances_km=tuple(sorted(strays)),
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
