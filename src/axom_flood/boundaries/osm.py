"""Match OpenStreetMap admin relations to Assam revenue circles.

Why this is not just a name lookup
----------------------------------
`build_osm_places.py` matched a circle to a relation by folded name alone. That
worked while the outlines were only ever drawn, and it silently broke 27 circles.

The Census files a circle that straddles a district line twice, once per
district, each suffixed "(Pt)". OSM files the same split as two relations, one
inside each district. Folding "(Pt)" away collapsed both halves onto one key, so
both localities matched both relations, and a later de-duplication step keyed on
the locality set kept exactly one relation and threw the other away. The
surviving outline was then drawn for both halves. Measured against village
points that were never derived from the boundary, Biswanath scored 0%, Lanka
scored 0%, and Dhekiajuli's two halves scored 17% and 0%.

Two names also repeat across the state without being a split at all: Lakhipur is
a circle in Goalpara *and* a different circle in Cachar, and Goreswar exists in
both Tamulpur and Kamrup. Name-only matching cannot tell those apart either.

So a circle is identified by name *and* district, and the district comes from
geometry rather than from a tag, because tags disagree with the Census about
which district a circle is in wherever a new district has been carved out.

Districts move; land does not
-----------------------------
Assam has created eight districts since the 2011 Census, and the locality file
carries a mix: modern district names, but circle splits recorded against the
older arrangement. A circle the Census files under Barpeta can therefore sit
inside OSM's Bajali, because Bajali was carved out of Barpeta in 2020. The
succession table below records those relationships so the same piece of land is
recognised under either name. It is deliberately one-directional and explicit:
it never merges two districts that were always separate.

Nothing here guesses. A circle that cannot be resolved to exactly one relation
is returned as unresolved, with the reason, and stays out of the analysis-grade
output entirely.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from axom_flood.geometry import Ring, point_in_rings

# OSM writes some Assam circle names differently from the Census. Only naming
# conventions are listed -- a "tehsil" suffix, a documented spelling variant.
# Genuine mismatches are reported as unresolved, never aliased away.
CIRCLE_ALIASES = {
    "dhekiajulitehsil": "dhekiajuli",
    "harisingatehsil": "harisinga",
    "khoirabaritehsil": "khoirabari",
    "mazbattehsil": "mazbat",
    "udalguritehsil": "udalguri",
    "moranassam": "moran",
    "marigaon": "morigaon",
    "golakganj": "golokganj",
}

# Relations inside the Assam query area that are not Assam revenue circles.
# "New Seren Circle" and "Sunpura Circle" are Arunachal administrative circles
# that share the word; they are not revenue circles of Assam.
NOT_ASSAM = {
    "maenchhunganglam",
    "newserencircle",
    "norbooganggewog",
    "norboogangrinchhenzor",
    "sunpuracircle",
}

# OSM district names that differ from the locality file's.
DISTRICT_ALIASES = {
    "hailakandidistrict": "hailakandi",
    "marigaon": "morigaon",
    # Karimganj was renamed Sribhumi in 2024. OSM still carries the old name.
    "karimganj": "sribhumi",
}

# New district -> the district its land was taken from. Used only to recognise
# that a locality filed under the parent may sit inside the child's outline.
# Every entry is a district creation, with the year it took effect.
DISTRICT_SUCCESSION = {
    "westkarbianglong": "karbianglong",  # 2016
    "bajali": "barpeta",  # 2020
    "tamulpur": "baksa",  # 2022
    "biswanath": "sonitpur",  # 2015
    "hojai": "nagaon",  # 2015
    "charaideo": "sivasagar",  # 2015
    "majuli": "jorhat",  # 2016
    "southsalmaramankachar": "dhubri",  # 2016
    "kamrupmetropolitan": "kamrup",  # 2003
}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def circle_key(value: str) -> str:
    """Fold a circle name to the form shared by OSM and the Census.

    The "(Pt)" suffix is dropped because it says which *half* of a split circle
    this is, not which circle. The district decides the half.
    """
    key = normalize(value)
    key = re.sub(r"pt(i{1,3}|[0-9]+)?$", "", key)
    return CIRCLE_ALIASES.get(key, CIRCLE_ALIASES.get(normalize(value), key))


def district_key(value: str) -> str:
    key = normalize(value)
    return DISTRICT_ALIASES.get(key, key)


def district_matches(locality_district: str, relation_district: str) -> bool:
    """Whether a locality's district and a relation's district are the same land.

    True when they fold to the same key, or when the relation sits in a district
    that was carved out of the locality's.
    """
    want = district_key(locality_district)
    have = district_key(relation_district)
    return have == want or DISTRICT_SUCCESSION.get(have) == want


def stitch_rings(members: list[dict[str, Any]]) -> list[Ring]:
    """Join an OSM relation's way members into closed rings.

    A boundary relation is a bag of unordered, arbitrarily directed ways. They
    have to be walked end to end before the outline means anything.
    """
    segments = [
        [[member_point["lon"], member_point["lat"]] for member_point in member["geometry"]]
        for member in members
        if member.get("type") == "way"
        and member.get("role") in {"outer", ""}
        and member.get("geometry")
    ]
    rings: list[Ring] = []
    while segments:
        current = segments.pop()
        joined = True
        while joined and current[0] != current[-1]:
            joined = False
            for index, segment in enumerate(segments):
                if segment[0] == current[-1]:
                    current += segment[1:]
                elif segment[-1] == current[-1]:
                    current += segment[-2::-1]
                elif segment[-1] == current[0]:
                    current = segment[:-1] + current
                elif segment[0] == current[0]:
                    current = segment[::-1][:-1] + current
                else:
                    continue
                segments.pop(index)
                joined = True
                break
        if len(current) >= 4 and current[0] == current[-1]:
            rings.append(current)
    return rings


@dataclass
class Relation:
    """One OSM administrative relation with its geometry resolved."""

    osm_id: int
    name: str
    admin_level: str
    rings: list[Ring]
    district: str | None = None
    district_share: float = 0.0

    @property
    def key(self) -> str:
        return circle_key(self.name)


@dataclass
class MatchResult:
    """One relation per locality where that is knowable, and the candidates where it is not.

    `matched` is the only safe input to anything computed — a rainfall average, a
    terrain band, a report's placement. `ambiguous` exists because the map has a
    weaker requirement than the analysis does: it can draw an outline and ask
    which half of a split circle the reader means, where an average cannot ask
    anybody. Dropping those circles from the map instead would take real place
    names out of search to buy a certainty the map never needed.
    """

    matched: dict[str, Relation] = field(default_factory=dict)
    ambiguous: dict[str, list[Relation]] = field(default_factory=dict)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    unused: list[Relation] = field(default_factory=list)


def load_relations(elements: list[dict[str, Any]]) -> tuple[list[Relation], list[Relation]]:
    """Split an Overpass payload into district (level 5) and circle (level 6) relations."""
    districts: list[Relation] = []
    circles: list[Relation] = []
    for element in elements:
        tags = element.get("tags") or {}
        level = tags.get("admin_level")
        if level not in {"5", "6"}:
            continue
        name = tags.get("name") or ""
        rings = stitch_rings(element.get("members") or [])
        if not rings:
            continue
        relation = Relation(
            osm_id=element.get("id", 0), name=name, admin_level=level, rings=rings
        )
        (districts if level == "5" else circles).append(relation)
    return districts, circles


def assign_districts(circles: list[Relation], districts: list[Relation], stride: int = 3) -> None:
    """Record which district each circle sits in, by majority of its own vertices.

    A single representative point is not enough. Assam's circles follow rivers
    and are often deeply concave, and a point chosen from one of them can land in
    the neighbouring district — Kaliabor, which wraps around the Kolong, resolved
    to Karbi Anglong that way. Counting vertices is insensitive to shape.

    `stride` subsamples the ring: these are full-resolution outlines with tens of
    thousands of vertices each, and every third one settles the question.
    """
    for circle in circles:
        vertices = [point for ring in circle.rings for point in ring][::stride]
        if not vertices:
            continue
        tally: Counter[str] = Counter()
        for vertex in vertices:
            for district in districts:
                if point_in_rings(vertex, district.rings):
                    tally[district.name] += 1
                    break
        if not tally:
            continue
        name, count = tally.most_common(1)[0]
        circle.district = name
        circle.district_share = count / len(vertices)


def match_localities(
    localities: list[dict[str, Any]], circles: list[Relation]
) -> MatchResult:
    """Resolve each locality to exactly one OSM circle relation, or to nothing.

    Name first: most circle names occur once in the whole state, and for those the
    district is not needed and cannot help — the locality file and OSM sometimes
    disagree about which district a circle belongs to, and where the name is
    unique that disagreement is a labelling difference, not an ambiguity.

    District second, and only to choose between relations that share a name.
    """
    candidates: dict[str, list[Relation]] = {}
    for circle in circles:
        if normalize(circle.name) in NOT_ASSAM:
            continue
        candidates.setdefault(circle.key, []).append(circle)

    result = MatchResult()
    for locality in localities:
        locality_id = locality["locality_id"]
        name = locality["revenue_circle"]
        district = locality["district"]
        found = candidates.get(circle_key(name), [])

        if len(found) == 1:
            result.matched[locality_id] = found[0]
            continue
        if not found:
            result.unresolved.append({
                "locality_id": locality_id,
                "revenue_circle": name,
                "district": district,
                "reason": "no_relation_with_this_name",
                "detail": "OpenStreetMap carries no admin_level=6 relation under this name.",
                "resolvable_by_matching": False,
                "candidates": [],
            })
            continue

        # An exact district match beats a succession match. North Guwahati is
        # split between Kamrup and Kamrup Metropolitan, and Kamrup Metropolitan
        # was carved out of Kamrup — so succession alone calls both halves
        # "Kamrup" and makes a resolvable split look ambiguous. The half whose
        # district is named outright is the half that was meant.
        exact = [
            circle for circle in found
            if circle.district and district_key(circle.district) == district_key(district)
        ]
        same_district = exact or [
            circle for circle in found
            if circle.district and district_matches(district, circle.district)
        ]
        if len(same_district) == 1:
            result.matched[locality_id] = same_district[0]
            continue

        described = [
            {"osm_id": circle.osm_id, "name": circle.name, "district": circle.district}
            for circle in found
        ]
        result.ambiguous[locality_id] = same_district or found
        if len(same_district) > 1:
            result.unresolved.append({
                "locality_id": locality_id,
                "revenue_circle": name,
                "district": district,
                "reason": "several_relations_in_the_same_district",
                "detail": (
                    "Two or more relations share this name inside one district, so the "
                    "district cannot say which half this is. Needs a reviewed decision."
                ),
                "resolvable_by_matching": True,
                "candidates": described,
            })
        else:
            result.unresolved.append({
                "locality_id": locality_id,
                "revenue_circle": name,
                "district": district,
                "reason": "osm_has_no_relation_for_this_portion",
                "detail": (
                    "The name exists, but every relation carrying it sits in another "
                    "district. Assam's district reorganisations cut through circles "
                    "rather than moving whole ones, so a circle can hold a portion in "
                    "each of two districts — Baksa carries portions of Pathorighat, "
                    "Rangia, Barnagar and Baganpara, Kamrup carries Rangia (Pt) and "
                    "North Guwahati (Pt), Nalbari carries Baganpara (Pt) and Ghograpar "
                    "(Pt). Checked against district records 2026-07-31: the Census list "
                    "is right and OpenStreetMap has no relation for the portion. No "
                    "matching rule can resolve this; it needs government boundary data "
                    "or an OSM edit."
                ),
                "resolvable_by_matching": False,
                "candidates": described,
            })

    used = {id(relation) for relation in result.matched.values()}
    used |= {
        id(relation) for relations in result.ambiguous.values() for relation in relations
    }
    result.unused = [
        circle for circle in circles
        if id(circle) not in used and normalize(circle.name) not in NOT_ASSAM
    ]
    return result
