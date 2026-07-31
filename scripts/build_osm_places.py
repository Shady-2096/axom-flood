"""Build the OpenStreetMap place-name layer and revenue-circle map shapes.

Run with:
  uv run python scripts/build_osm_places.py \
    --places data/reference/osm/assam-places-<sha>.json \
    --boundaries data/reference/osm/assam-boundaries-<sha>.json

Why this exists alongside the Census artifacts
----------------------------------------------
The Census only names administrative units. Gaurisagar, a town on NH-2 that
everyone in the area calls Gaurisagar, is not one: the Census 2011 rural
directory records that land as the villages "Phukan Phadia" and "Namdangia
Bongali", the 2001 urban directory does not list it, and Census 2011 gives
Sivasagar district exactly seven towns, none of them Gaurisagar. Someone
searching the name they actually use therefore found nothing.

OpenStreetMap does carry these names, so this script adds them as a *second*
layer beside the Census village index rather than replacing it. It also emits
the revenue-circle outlines the picker map draws, from the same download, so a
place and the shape it sits in can never disagree.

Every place is assigned to a revenue circle by testing which circle outline
contains it. Nearest-centre assignment is deliberately not used as a fallback:
a place placed in the wrong circle would show a river reading from the wrong
gauge, and no name is worth that. Places that land in no circle are dropped and
counted in the report.

OpenStreetMap data is ODbL. Anything published from these artifacts has to
carry the "© OpenStreetMap contributors" credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from axom_flood.boundaries.osm import (
    assign_districts,
    load_relations,
    match_localities,
    normalize,
)

SOURCE_QUERY_PLACES = (
    'area["ISO3166-2"="IN-AS"]->.a;'
    '(node(area.a)["place"~"^(city|town|village|hamlet|suburb|neighbourhood'
    '|quarter|isolated_dwelling)$"];'
    'way(area.a)["place"~"^(city|town|village|hamlet|suburb|neighbourhood'
    '|quarter)$"];);out tags center;'
)
SOURCE_QUERY_BOUNDARIES = (
    'area["ISO3166-2"="IN-AS"]->.a;'
    'relation(area.a)["boundary"="administrative"]["admin_level"~"^(5|6)$"];out geom;'
)
ATTRIBUTION = "© OpenStreetMap contributors, ODbL"

# Place kinds worth offering as a search result. Anything smaller than a hamlet
# is noise in a list someone reads under stress.
PLACE_RANK = {
    "city": 0,
    "town": 1,
    "suburb": 2,
    "village": 3,
    "quarter": 4,
    "neighbourhood": 5,
    "hamlet": 6,
    "isolated_dwelling": 7,
}

def ring_area(ring: list[list[float]]) -> float:
    total = 0.0
    for index in range(len(ring)):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index]
        x2, y2 = ring[(index - 1) % count]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def simplify(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker, so the map ships as kilobytes rather than megabytes.

    The simplified outline is only ever drawn. Assignment of a place to a circle
    is done against the full-resolution ring, so trimming a coastline here can
    never move somebody into the wrong circle.
    """
    if len(ring) < 4:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    # A ring starts and ends on the same point, so a single pass would measure
    # every vertex against a zero-length baseline and keep all of them. Anchor a
    # second point at the far side and simplify the two arcs between them.
    far = max(
        range(1, len(ring) - 1),
        key=lambda index: (ring[index][0] - ring[0][0]) ** 2 + (ring[index][1] - ring[0][1]) ** 2,
    )
    keep[far] = True
    stack = [(0, far), (far, len(ring) - 1)]
    while stack:
        start, end = stack.pop()
        x1, y1 = ring[start]
        x2, y2 = ring[end]
        worst, worst_index = tolerance, -1
        for index in range(start + 1, end):
            x0, y0 = ring[index]
            numerator = abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1))
            denominator = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1e-12
            distance = numerator / denominator
            if distance > worst:
                worst, worst_index = distance, index
        if worst_index > 0:
            keep[worst_index] = True
            stack += [(start, worst_index), (worst_index, end)]
    simplified = [point for point, keeping in zip(ring, keep, strict=True) if keeping]
    return simplified if len(simplified) >= 4 else ring


def load(path: Path) -> tuple[list[dict[str, Any]], str]:
    payload = path.read_bytes()
    return json.loads(payload)["elements"], hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--places", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=0.002)
    parser.add_argument("--places-out", type=Path,
                        default=Path("config/assam-osm-places.json"))
    parser.add_argument("--shapes-out", type=Path,
                        default=Path("config/assam-circle-shapes.json"))
    args = parser.parse_args()

    localities = json.loads(Path("config/assam-localities.json").read_text())["localities"]
    places, places_hash = load(args.places)
    boundaries, boundaries_hash = load(args.boundaries)

    # Matching lives in `axom_flood.boundaries.osm` because the analysis-grade
    # boundary build needs exactly the same answer, and the two drifting apart
    # would mean the map draws one circle while the rainfall average is computed
    # over another.
    #
    # It replaces a name-only match that folded "(Pt)" away and so collapsed both
    # halves of every split circle onto one key. A later de-duplication step then
    # kept one relation per locality set and threw the other away, and the
    # survivor was drawn for both halves. Twenty-seven circle names are split
    # that way. Measured against school points that were never derived from a
    # boundary, Biswanath scored 0% and Dhekiajuli's two halves scored 17% and 0%.
    districts, relations = load_relations(boundaries)
    assign_districts(relations, districts)
    match = match_localities(localities, relations)

    by_id = {locality["locality_id"]: locality for locality in localities}
    grouped: dict[int, dict[str, Any]] = {}

    def attach(locality_id: str, relation: Any) -> None:
        entry = grouped.setdefault(
            id(relation), {"name": relation.name, "rings": relation.rings, "localities": []}
        )
        entry["localities"].append(by_id[locality_id])

    for locality_id, relation in match.matched.items():
        attach(locality_id, relation)
    # A locality the analysis build refuses to place still gets drawn, on every
    # outline it could plausibly be. The search screen already asks which circle
    # a name belongs to when a shape carries more than one, so the reader
    # resolves what the data cannot. Leaving these out would silently drop real
    # place names from search to buy a certainty the map does not need.
    for locality_id, relations in match.ambiguous.items():
        for relation in relations:
            attach(locality_id, relation)

    circles = list(grouped.values())
    for circle in circles:
        circle["localities"].sort(key=lambda locality: locality["locality_id"])

    # Outlines carrying more than one locality: either OSM does not model a
    # Census split at all, or it models one the Census records differently.
    undecided = [c["name"] for c in circles if len(c["localities"]) > 1]
    uncovered = [
        item["revenue_circle"] for item in match.unresolved
        if item["locality_id"] not in match.ambiguous
    ]
    unmatched_osm = [
        f"{relation.name} ({relation.district})" for relation in match.unused
    ]

    assigned = []
    dropped = 0
    for element in places:
        tags = element.get("tags", {})
        name = tags.get("name")
        kind = tags.get("place")
        if not name or kind not in PLACE_RANK:
            continue
        centre = element.get("center") or element
        try:
            point = (round(float(centre["lon"]), 5), round(float(centre["lat"]), 5))
        except (KeyError, TypeError, ValueError):
            continue
        home = next(
            (circle for circle in circles
             if any(point_in_ring(point, ring) for ring in circle["rings"])),
            None,
        )
        if home is None:
            dropped += 1
            continue
        entry = {
            "place_name": name,
            "normalized_name": normalize(name),
            "place_kind": kind,
            "centre": list(point),
            # Usually one. Two where the outline is a circle the Census split
            # across districts, and the search screen asks which rather than
            # picking a side.
            "locality_ids": [locality["locality_id"] for locality in home["localities"]],
            "revenue_circle": home["localities"][0]["revenue_circle"],
            "district": home["localities"][0]["district"],
            "osm_id": f"{element['type']}/{element['id']}",
        }
        for tag, field in (("name:as", "name_as"), ("alt_name", "alt_name")):
            if tags.get(tag):
                entry[field] = tags[tag]
        assigned.append(entry)

    assigned.sort(key=lambda item: (PLACE_RANK[item["place_kind"]], item["place_name"]))
    places_document = {
        "schema_version": 1,
        "attribution": ATTRIBUTION,
        "places": assigned,
        "provenance": {
            "source": "OpenStreetMap via Overpass API",
            "licence": "ODbL 1.0",
            "query": SOURCE_QUERY_PLACES,
            "payload_sha256": places_hash,
            "assignment": "point-in-polygon against OSM admin_level=6 outlines",
        },
    }

    shapes_document = {
        "schema_version": 1,
        "attribution": ATTRIBUTION,
        "circles": [
            {
                "locality_ids": [
                    locality["locality_id"] for locality in circle["localities"]
                ],
                "revenue_circle": circle["localities"][0]["revenue_circle"],
                "district": circle["localities"][0]["district"],
                # Rounded to four decimals, about 11 m, which is finer than a
                # simplified outline resolves and roughly halves the payload.
                "rings": [
                    [[round(x, 4), round(y, 4)] for x, y in simplify(ring, args.tolerance)]
                    for ring in sorted(circle["rings"], key=ring_area, reverse=True)[:2]
                ],
            }
            for circle in circles
        ],
        "provenance": {
            "source": "OpenStreetMap via Overpass API",
            "licence": "ODbL 1.0",
            "query": SOURCE_QUERY_BOUNDARIES,
            "payload_sha256": boundaries_hash,
            "simplification": f"Ramer-Douglas-Peucker, tolerance {args.tolerance} degrees",
            "note": "Outlines are for drawing only and are not used to place anyone.",
        },
    }

    for path, document in ((args.places_out, places_document), (args.shapes_out, shapes_document)):
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print(f"localities matched   {len(match.matched)} of {len(localities)} "
          f"({len(circles)} distinct outlines)")
    print(f"places kept          {len(assigned)} ({dropped} fell outside every circle)")
    print(f"shapes written       {args.shapes_out} "
          f"({args.shapes_out.stat().st_size / 1024:.0f} KiB)")
    print(f"places written       {args.places_out} "
          f"({args.places_out.stat().st_size / 1024:.0f} KiB)")
    if unmatched_osm:
        print(f"OSM circles with no Census match ({len(unmatched_osm)}): "
              f"{', '.join(sorted(unmatched_osm))}")
    if undecided:
        print(f"circles carrying both halves of a split, so the map asks "
              f"({len(undecided)}): {', '.join(sorted(undecided))}")
    if uncovered:
        print(f"localities with no outline ({len(uncovered)}): {', '.join(sorted(uncovered))}")


if __name__ == "__main__":
    main()
