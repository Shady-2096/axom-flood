"""Decide which of a village name's schools are actually in that village.

The problem
-----------
Every school coordinate this project uses reaches a village through one join:
the district and village name UDISE recorded, folded and matched against the
Census 2011 village list. Names are not unique. "Jamuguri", "Chandmari" and
"No. 2 Chakala" occur many times over, and the district column is not fine
enough to separate them — Biswanath alone is about 130 km across.

So a single name key can collect schools that are nowhere near each other. The
worst measured case put six schools under one name with 116 km between the
furthest pair. The join had no way to notice, because it only ever asked whether
the name matched.

What that broke
---------------
Three things downstream, all of which look like different bugs:

- a village's stored centre is the median of its schools, so a name that matched
  two clusters put the centre in the empty space between them. Searching for the
  village on the site then dropped a pin tens of kilometres from the village.
- a circle's centroid is the median of its villages' centres, and the centroid is
  what the gauge distance is measured from.
- a circle boundary is scored by asking whether its own schools fall inside its
  outline. Schools from the other end of the district fall outside, and the
  outline takes the blame for a join error.

The rule
--------
Schools in one village are near each other. Take the median of the key's schools
and keep those within `VILLAGE_RADIUS_KM` of it. If the kept points are not a
strict majority, the schools do not agree where the village is and none of them
can be trusted to say — the whole key is dropped.

Dropping is the right failure. A wrong coordinate is worse than a missing one
here: a missing village has no centre and is skipped everywhere, while a wrong
one is indistinguishable from a real answer and quietly corrupts a boundary
score, a centroid, and a search result.

Choosing the radius
-------------------
Measured over the 5,613 name keys that survive the existing uniqueness guard,
the spread from the median runs 0.7 km at the median key, 1.8 km at the 75th
percentile and 2.9 km at the 80th, then jumps to 7.2 km at the 85th and 14.5 km
at the 90th. That is two populations, not one distribution: real villages a
couple of kilometres across, and name collisions tens of kilometres apart. Five
kilometres sits in the empty ground between them, so the exact value does not
decide much — which is the property to want from a threshold.

Assam holds about 26,000 villages over 78,438 km², so the average one is under
two kilometres across. A five-kilometre radius is already generous to a large
riverine or tea-estate village.

The number of circle boundaries that pass Workstream 0 does move with the
radius — 82 with no guard at all, then 107 at 2 km, 102 at 5 km, and 94 at 15 km.
That is a slope, so it is worth saying plainly that the radius chosen is not the
one that passes the most circles. It is the one that matches how big a village
is. A tighter radius would pass five more circles by discarding schools that are
genuinely in the village it is scoring.
"""

from __future__ import annotations

from math import cos, hypot, radians
from statistics import median

#: How far from the median of its own schools a school may sit and still be
#: taken as part of the same village. See the module docstring for the measured
#: reason this is 5 and not 2 or 15.
VILLAGE_RADIUS_KM = 5.0

# A degree of latitude is 110.57 km throughout Assam; a degree of longitude
# shrinks with the cosine of the latitude. Assam spans roughly 24-28°N, and
# taking the middle costs about 2% in the longitude scale at the edges — metres
# on a five-kilometre test.
_KM_PER_DEGREE_LAT = 110.57
_KM_PER_DEGREE_LON = 111.32 * cos(radians(26.0))

Point = tuple[float, float]


def _distance_km(point: Point, other: Point) -> float:
    return hypot(
        (point[0] - other[0]) * _KM_PER_DEGREE_LON,
        (point[1] - other[1]) * _KM_PER_DEGREE_LAT,
    )


def coherent_village_points(
    points: list[Point], radius_km: float = VILLAGE_RADIUS_KM
) -> list[Point]:
    """The schools that agree on where the village is, or nothing.

    A single school is returned unchanged: one point cannot disagree with itself,
    and the name may well be unique. Two schools far apart return nothing,
    because neither has any claim over the other.
    """
    if len(points) < 2:
        return list(points)

    centre = (
        median(point[0] for point in points),
        median(point[1] for point in points),
    )
    kept = [point for point in points if _distance_km(point, centre) <= radius_km]
    # A strict majority, so a key split evenly between two places is refused
    # rather than awarded to whichever cluster the median happened to land in.
    if len(kept) * 2 <= len(points):
        return []
    return kept
